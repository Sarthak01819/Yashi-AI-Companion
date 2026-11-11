#!/usr/bin/env python3
"""
Yashi as a Windows app: one window, no terminal, no Node needed to start.

    pythonw desktop.py        (what the Yashi shortcut runs)
    python  desktop.py        same, with log output in the console

The backend runs in a background thread and serves the production build of
frontend/ on http://127.0.0.1:8000. If the frontend source is newer than that
build (you changed the code), it is rebuilt first. Closing the window stops
everything.

Create the Desktop / Start Menu shortcut with:  python tools/make_shortcut.py
"""

import os
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
sys.path.insert(0, str(ROOT))

# pythonw has no console: sys.stdout is None and any print/log would crash.
if sys.stdout is None or sys.stderr is None:
    (ROOT / "logs").mkdir(exist_ok=True)
    _log = open(ROOT / "logs" / "desktop.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stdout or _log
    sys.stderr = sys.stderr or _log

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["YASHI_SERVE_UI"] = "1"          # backend serves frontend/dist (see app/main.py)

from config.settings import PORT  # noqa: E402

URL = f"http://127.0.0.1:{PORT}"
FRONTEND = ROOT / "frontend"
DIST_INDEX = FRONTEND / "dist" / "index.html"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

SCREEN = """<!doctype html><html><body style="margin:0;height:100vh;display:grid;place-items:center;
background:#0c0708;color:#fff;font:600 15px 'Segoe UI',sans-serif">
<div style="text-align:center"><div style="font:900 42px 'Segoe UI';letter-spacing:.3em;color:#ff5c7a">YASHI</div>
<div style="margin-top:14px;opacity:.7">{message}</div></div></body></html>"""


def _newest_mtime(*paths: Path) -> float:
    newest = 0.0
    for path in paths:
        if path.is_file():
            newest = max(newest, path.stat().st_mtime)
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.is_file():
                    newest = max(newest, f.stat().st_mtime)
    return newest


def build_is_stale() -> bool:
    if not DIST_INDEX.exists():
        return True
    sources = _newest_mtime(FRONTEND / "src", FRONTEND / "public", FRONTEND / "index.html",
                            FRONTEND / "package.json", FRONTEND / "vite.config.js")
    return sources > DIST_INDEX.stat().st_mtime


def build_frontend() -> bool:
    import shutil
    npm = shutil.which("npm")
    if not npm:
        return DIST_INDEX.exists()          # no Node: keep using the last build
    if not (FRONTEND / "node_modules").exists():
        subprocess.run([npm, "install"], cwd=FRONTEND, creationflags=NO_WINDOW, check=False)
    result = subprocess.run([npm, "run", "build"], cwd=FRONTEND, creationflags=NO_WINDOW,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    print(result.stdout[-2000:])
    return result.returncode == 0 or DIST_INDEX.exists()


def is_up(url: str) -> bool:
    import urllib.request
    try:
        urllib.request.urlopen(url, timeout=1)
        return True
    except Exception:
        return False


def serves_ui() -> bool:
    import urllib.request
    try:
        with urllib.request.urlopen(URL + "/", timeout=2) as response:
            return "text/html" in response.headers.get("content-type", "")
    except Exception:
        return False


def start_server():
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=PORT, reload=False,
                log_level="warning", access_log=False, log_config=None)


# ?mic=1 tells the page to switch the microphone on once it's connected.
APP_URL = URL + "/?mic=1"


def open_app(window):
    allow_microphone(window)
    window.load_url(APP_URL)


def boot(window):
    """Runs once the window is up: build if needed, start the backend, show the app."""
    def show(message):
        window.load_html(SCREEN.format(message=message))

    if is_up(URL + "/health"):
        # Yashi is already running. Another desktop window: just attach to it.
        if serves_ui():
            open_app(window)
        else:
            show("Yashi is already running in the browser version (run.py).<br>"
                 "Close that terminal first, then open the app again.")
        return

    if build_is_stale():
        show("Updating Yashi...")
        if not build_frontend():
            show("Couldn't build the app. Run <code>npm run build</code> in frontend/ to see why.")
            return

    show("Waking Yashi up...")
    threading.Thread(target=start_server, daemon=True).start()
    deadline = time.time() + 60
    while time.time() < deadline:
        if is_up(URL + "/health"):
            open_app(window)
            return
        time.sleep(0.3)
    show("Yashi's backend didn't start. See logs/desktop.log for the error.")


def unblock_webview_dlls():
    """
    Windows tags pip-downloaded DLLs as "from the internet" (a Zone.Identifier
    stream) and .NET then refuses to load pywebview's WebView2 DLLs. Remove the
    tag from those package files only.
    """
    if os.name != "nt":
        return
    import importlib.util
    for package in ("webview", "pythonnet", "clr_loader"):
        spec = importlib.util.find_spec(package)
        if not spec or not spec.submodule_search_locations:
            continue
        for folder in spec.submodule_search_locations:
            for dll in Path(folder).rglob("*.dll"):
                try:
                    os.remove(f"{dll}:Zone.Identifier")
                except OSError:
                    pass                    # not tagged


# Must match tools/make_shortcut.py: Windows groups taskbar buttons by this ID,
# so the window and the (pinned) shortcut share one button with Yashi's icon
# instead of showing up as pythonw.exe.
APP_ID = "Yashi.AICompanion"
ICON = ROOT / "assets" / "yashi.ico"


def set_app_id():
    if os.name == "nt":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)


def set_window_icon(window):
    """
    pywebview's WinForms backend always gives the window pythonw.exe's icon
    (title bar and taskbar). Swap in Yashi's, on the WinForms UI thread.
    """
    if os.name != "nt" or not ICON.exists():
        return
    try:
        from System import Action
        from System.Drawing import Icon
        form = window.native

        def apply():
            form.Icon = Icon(str(ICON))

        if form.InvokeRequired:
            form.Invoke(Action(apply))
        else:
            apply()
    except Exception as error:                  # cosmetic: never block startup
        print("Could not set the window icon:", repr(error))


def allow_microphone(window):
    """
    Let Yashi's own page use the mic without WebView2 asking on every launch.
    Only for the local app URL; any other page still gets the normal prompt.
    """
    if os.name != "nt":
        return
    try:
        from System import Action
        from Microsoft.Web.WebView2.Core import CoreWebView2PermissionKind, CoreWebView2PermissionState
        form = window.native
        webview = form.browser.webview

        def on_permission(sender, args):
            if args.PermissionKind == CoreWebView2PermissionKind.Microphone and args.Uri.startswith(URL):
                args.State = CoreWebView2PermissionState.Allow

        def hook():
            webview.CoreWebView2.PermissionRequested += on_permission

        deadline = time.time() + 10
        while webview.CoreWebView2 is None and time.time() < deadline:
            time.sleep(0.2)                       # WebView2 still initialising
        form.Invoke(Action(hook))
    except Exception as error:
        print("Could not pre-allow the microphone:", repr(error))


def main():
    unblock_webview_dlls()
    set_app_id()
    # Lets the page start audio (mic analysis, Yashi's voice) without a click first.
    os.environ.setdefault("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "--autoplay-policy=no-user-gesture-required")
    import webview

    window = webview.create_window(
        "Yashi - AI Companion",
        html=SCREEN.format(message="Starting..."),
        width=1320, height=840, min_size=(900, 600),
        background_color="#0c0708", text_select=True,
    )
    window.events.shown += lambda: set_window_icon(window)
    # Keep localStorage etc. between launches, inside the project folder.
    webview.start(boot, window, private_mode=False, storage_path=str(ROOT / "data" / "webview"))


if __name__ == "__main__":
    main()
