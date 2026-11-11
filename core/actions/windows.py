"""
Low-level Windows helpers: installed apps, top-level windows, keyboard and
volume. Everything blocking here is called through asyncio.to_thread.
"""
import ctypes
import difflib
import json
import logging
import os
import re
import subprocess
import time
from ctypes import wintypes
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)

IS_WINDOWS = os.name == "nt"
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
user32 = ctypes.windll.user32 if IS_WINDOWS else None
kernel32 = ctypes.windll.kernel32 if IS_WINDOWS else None


def powershell(script: str, timeout: float = 20) -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                         capture_output=True, text=True, timeout=timeout, creationflags=NO_WINDOW)
    return out.stdout


# ── Installed apps (everything in the Start menu, incl. Store apps) ──────────
_apps_cache: dict = {"at": 0.0, "apps": []}

# Spoken names -> how the app is called in the Start menu.
APP_ALIASES = {
    "vs code": "visual studio code", "vscode": "visual studio code", "code": "visual studio code",
    "chrome": "google chrome", "edge": "microsoft edge", "word": "word", "excel": "excel",
    "powerpoint": "powerpoint", "cmd": "command prompt", "terminal": "terminal",
    "calculator": "calculator", "calc": "calculator", "settings": "settings",
    "file explorer": "file explorer", "explorer": "file explorer", "files": "file explorer",
    "task manager": "task manager", "camera": "camera", "photos": "photos",
    "telegram": "telegram desktop", "whatsapp": "whatsapp", "notepad": "notepad",
}

# Apps that are not in the Start menu list but always exist.
BUILTIN_COMMANDS = {
    "file explorer": ["explorer.exe"],
    "task manager": ["taskmgr.exe"],
    "command prompt": ["cmd.exe"],
    "control panel": ["control.exe"],
}


def start_apps(max_age: float = 600) -> List[dict]:
    if not IS_WINDOWS:
        return []
    if time.time() - _apps_cache["at"] < max_age and _apps_cache["apps"]:
        return _apps_cache["apps"]
    try:
        raw = powershell("Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress")
        apps = json.loads(raw) if raw.strip() else []
        apps = [apps] if isinstance(apps, dict) else apps
    except Exception as error:
        logger.warning("Could not list Start menu apps: %s", error)
        apps = []
    _apps_cache.update(at=time.time(), apps=apps)
    return apps


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9+ ]", " ", text.lower()).strip()


def find_app(name: str) -> Optional[dict]:
    """Best Start-menu match for a spoken app name, or None."""
    wanted = _norm(APP_ALIASES.get(_norm(name), name))
    if not wanted:
        return None
    if wanted in BUILTIN_COMMANDS:
        return {"Name": wanted.title(), "command": BUILTIN_COMMANDS[wanted]}
    apps = start_apps()
    names = {_norm(a["Name"]): a for a in apps if a.get("Name")}
    if wanted in names:
        return names[wanted]
    # "spotify" -> "Spotify Music", but not "uninstall spotify"
    starts = [a for n, a in names.items() if n.startswith(wanted + " ") and "uninstall" not in n]
    if starts:
        return min(starts, key=lambda a: len(a["Name"]))
    words = [a for n, a in names.items() if wanted in n.split() and "uninstall" not in n]
    if words:
        return min(words, key=lambda a: len(a["Name"]))
    close = difflib.get_close_matches(wanted, list(names), n=1, cutoff=0.82)
    return names[close[0]] if close else None


def launch_app(app: dict) -> bool:
    try:
        if "command" in app:
            subprocess.Popen(app["command"], creationflags=NO_WINDOW)
        else:
            # Works for Store apps and classic desktop apps alike.
            subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{app['AppID']}"])
        return True
    except Exception as error:
        logger.warning("Launch failed for %s: %s", app, error)
        return False


# ── Windows ──────────────────────────────────────────────────────────────────
@dataclass
class Window:
    hwnd: int
    title: str
    process: str          # exe name without .exe, lower case


def _process_name(pid: int) -> str:
    handle = kernel32.OpenProcess(0x1000, False, pid)        # PROCESS_QUERY_LIMITED_INFORMATION
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(512)
        size = wintypes.DWORD(512)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buf, ctypes.byref(size)):
            return os.path.splitext(os.path.basename(buf.value))[0].lower()
        return ""
    finally:
        kernel32.CloseHandle(handle)


def list_windows() -> List[Window]:
    if not IS_WINDOWS:
        return []
    found: List[Window] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _):
        if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):    # GW_OWNER: skip popups
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, title, length + 1)
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        found.append(Window(int(hwnd), title.value, _process_name(pid.value)))
        return True

    user32.EnumWindows(visit, 0)
    return [w for w in found if w.title not in ("Program Manager", "Windows Input Experience")]


def find_windows(name: str) -> List[Window]:
    """Windows whose title or process matches a spoken app name."""
    wanted = _norm(APP_ALIASES.get(_norm(name), name))
    key = wanted.replace(" ", "")
    hits = []
    for w in list_windows():
        title, proc = _norm(w.title), w.process.replace(" ", "")
        if key and (key in proc or proc in key and len(proc) > 3 or wanted in title):
            hits.append(w)
    return hits


def focus(hwnd: int) -> bool:
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)                      # SW_RESTORE
    # Windows only lets the foreground app hand over focus; a tap of Alt
    # counts as user input and unlocks SetForegroundWindow.
    user32.keybd_event(0x12, 0, 0, 0)
    user32.keybd_event(0x12, 0, 2, 0)
    ok = bool(user32.SetForegroundWindow(hwnd))
    time.sleep(0.15)
    return ok


YASHI_TITLE = "Yashi - AI Companion"


def snapshot(name: str) -> dict:
    return {w.hwnd: w.title for w in find_windows(name)}


def wait_for_window(name: str, before: dict, timeout: float = 8.0) -> Optional[Window]:
    """
    After launching an app: wait until it shows something new (a new window,
    or a new tab changing an existing window's title), let it settle, then
    bring it to the front. Typing straight away would be lost, or land in a
    tab that was already open.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        for w in find_windows(name):
            if before.get(w.hwnd) != w.title:
                time.sleep(0.6)
                focus(w.hwnd)
                return w
        time.sleep(0.25)
    # Single-window apps that were already open just come to the front.
    current = find_windows(name)
    if current:
        focus(current[0].hwnd)
        return current[0]
    return None


def leave_yashi() -> None:
    """
    Typing or shortcuts are meant for the app the user was using, not Yashi's
    own window (which is focused while they talk to her). EnumWindows walks
    top-to-bottom, so the first other window is the one used last.
    """
    foreground = user32.GetForegroundWindow()
    length = user32.GetWindowTextLengthW(foreground)
    title = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(foreground, title, length + 1)
    if YASHI_TITLE not in title.value and "Yashi" not in title.value:
        return
    for w in list_windows():
        if w.hwnd != foreground and "Yashi" not in w.title and not user32.IsIconic(w.hwnd):
            focus(w.hwnd)
            return


def show(hwnd: int, how: str) -> None:
    user32.ShowWindow(hwnd, {"minimize": 6, "maximize": 3, "restore": 9}[how])


def close(hwnd: int) -> None:
    user32.PostMessageW(hwnd, 0x0010, 0, 0)            # WM_CLOSE: lets the app save first


# ── Keyboard ─────────────────────────────────────────────────────────────────
def _keyboard():
    from pynput.keyboard import Controller
    return Controller()


def type_text(text: str) -> None:
    _keyboard().type(text)


def _key(name: str):
    from pynput.keyboard import Key
    name = name.strip().lower()
    aliases = {"control": "ctrl", "win": "cmd", "windows": "cmd", "super": "cmd", "return": "enter",
               "escape": "esc", "del": "delete", "pgup": "page_up", "pgdn": "page_down",
               "arrowup": "up", "arrowdown": "down", "arrowleft": "left", "arrowright": "right"}
    name = aliases.get(name, name)
    if hasattr(Key, name):
        return getattr(Key, name)
    if len(name) == 1:
        return name
    raise ValueError(f"unknown key '{name}'")


def press_keys(combo: str) -> None:
    """'ctrl+shift+t', 'alt+tab', 'enter', 'f5'."""
    kb = _keyboard()
    keys = [_key(k) for k in combo.replace(" ", "").split("+") if k]
    for k in keys:
        kb.press(k)
    time.sleep(0.05)
    for k in reversed(keys):
        kb.release(k)


# ── Media & volume (virtual keys: work for any player) ───────────────────────
VK = {"mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF, "next": 0xB0,
      "previous": 0xB1, "stop": 0xB2, "play_pause": 0xB3}


def tap_vk(name: str, times: int = 1) -> None:
    for _ in range(max(1, times)):
        user32.keybd_event(VK[name], 0, 0, 0)
        user32.keybd_event(VK[name], 0, 2, 0)
        time.sleep(0.01)


def set_volume(percent: int) -> None:
    """Each volume key is 2%: go to zero, then up."""
    percent = max(0, min(100, int(percent)))
    tap_vk("volume_down", 50)
    if percent:
        tap_vk("volume_up", round(percent / 2))


# ── Power & screen ───────────────────────────────────────────────────────────
def lock() -> None:
    user32.LockWorkStation()


def sleep_pc() -> None:
    ctypes.windll.powrprof.SetSuspendState(False, True, False)


def screenshot(path: str) -> bool:
    script = (
        "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
        "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
        "$i=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
        "$g=[System.Drawing.Graphics]::FromImage($i);"
        "$g.CopyFromScreen($b.Left,$b.Top,0,0,$i.Size);"
        f"$i.Save('{path.replace(chr(39), chr(39) * 2)}');"
    )
    powershell(script)
    return os.path.exists(path)
