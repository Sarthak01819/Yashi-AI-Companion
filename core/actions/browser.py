"""
"Yashi's browser": a Chrome window with its own profile (data/yashi-browser)
that Yashi can drive — YouTube Music and WhatsApp Web live here. You log in
to those once in that window; the profile keeps you logged in.

Chrome is started normally with a local debugging port and Playwright attaches
to it over CDP, so sites see an ordinary Chrome (no automation banner).
Playwright's sync API runs on one dedicated thread; callers use `await run(fn)`
where fn(page_finder) does the page work.
"""
import asyncio
import concurrent.futures
import json
import logging
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "data" / "yashi-browser"
PORT = int(os.getenv("YASHI_BROWSER_PORT", "9223"))
ENDPOINT = f"http://127.0.0.1:{PORT}"

CHROME_PATHS = [
    os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%LocalAppData%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"),
    os.path.expandvars(r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"),
]

_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="yashi-browser")
_state = {"pw": None, "browser": None}


class BrowserUnavailable(RuntimeError):
    pass


def _chrome() -> str:
    for path in CHROME_PATHS:
        if os.path.isfile(path):
            return path
    found = shutil.which("chrome") or shutil.which("msedge")
    if not found:
        raise BrowserUnavailable("Chrome or Edge isn't installed")
    return found


def _debug_port_up() -> bool:
    try:
        with urllib.request.urlopen(ENDPOINT + "/json/version", timeout=1) as r:
            return "webSocketDebuggerUrl" in json.loads(r.read())
    except Exception:
        return False


def _launch_chrome(first_url: str = "about:blank") -> None:
    PROFILE.mkdir(parents=True, exist_ok=True)
    subprocess.Popen([
        _chrome(),
        f"--remote-debugging-port={PORT}",
        "--remote-debugging-address=127.0.0.1",
        f"--user-data-dir={PROFILE}",
        "--no-first-run", "--no-default-browser-check",
        "--autoplay-policy=no-user-gesture-required",   # music starts without a click
        first_url,
    ], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    deadline = time.time() + 20
    while time.time() < deadline:
        if _debug_port_up():
            return
        time.sleep(0.3)
    raise BrowserUnavailable("Yashi's browser didn't start")


def is_open(host: str) -> bool:
    """Is a tab on `host` open in Yashi's browser? Never starts the browser."""
    try:
        with urllib.request.urlopen(ENDPOINT + "/json/list", timeout=1) as r:
            return any(host in t.get("url", "") for t in json.loads(r.read()) if t.get("type") == "page")
    except Exception:
        return False


def _browser():
    """Connected Playwright Browser (starting Chrome if needed). Worker thread only."""
    browser = _state["browser"]
    if browser is not None and browser.is_connected() and _debug_port_up():
        return browser
    if not _debug_port_up():
        _launch_chrome()
    if _state["pw"] is None:
        from playwright.sync_api import sync_playwright
        _state["pw"] = sync_playwright().start()
    browser = _state["pw"].chromium.connect_over_cdp(ENDPOINT)
    _state["browser"] = browser
    return browser


class Pages:
    """Handed to the work function: find or open the tab for a site."""

    def __init__(self, browser):
        self.browser = browser
        self.context = browser.contexts[0] if browser.contexts else browser.new_context()

    def tab(self, host: str, url: str, navigate: bool = False):
        """The open tab on `host` (going to `url` if navigate), else a new one at `url`."""
        page = self.find(host)
        if page is not None:
            if navigate:
                page.goto(url, wait_until="domcontentloaded")
            page.bring_to_front()
            return page
        # Reuse the blank start tab instead of piling up tabs.
        blank = next((p for p in self.context.pages if p.url in ("about:blank", "chrome://newtab/")), None)
        page = blank or self.context.new_page()
        page.goto(url, wait_until="domcontentloaded")
        page.bring_to_front()
        return page

    def find(self, host: str):
        return next((p for p in self.context.pages if host in p.url), None)


def _call(fn):
    try:
        return fn(Pages(_browser()))
    except BrowserUnavailable:
        raise
    except Exception as error:
        # A closed window or a dropped connection: reconnect once and retry.
        logger.info("Browser action failed (%s), reconnecting", error)
        _state["browser"] = None
        return fn(Pages(_browser()))


async def run(fn):
    """Run fn(pages) on the browser thread."""
    return await asyncio.get_running_loop().run_in_executor(_executor, _call, fn)
