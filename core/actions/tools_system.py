"""Apps, windows, keyboard, volume and power."""
import asyncio
import subprocess
import time
from datetime import datetime
from pathlib import Path

from core.actions import windows as win
from core.actions.registry import Result, tool


@tool("open_app", "Open an installed app (Start-menu name, e.g. 'WhatsApp', 'VS Code', 'Calculator').",
      {"name": "app name"})
async def open_app(name: str) -> Result:
    app = await asyncio.to_thread(win.find_app, name)
    if not app:
        return Result(False, f"I couldn't find an app called {name} on this PC.")
    before = await asyncio.to_thread(win.snapshot, app["Name"])
    ok = await asyncio.to_thread(win.launch_app, app)
    if ok:
        # So a following "type ..." lands in this app.
        await asyncio.to_thread(win.wait_for_window, app["Name"], before)
    return Result(ok, f"Opening {app['Name']}." if ok else f"{app['Name']} didn't want to open.")


@tool("close_app", "Close an app's windows (it may ask to save).", {"name": "app name"})
async def close_app(name: str) -> Result:
    found = await asyncio.to_thread(win.find_windows, name)
    if not found:
        return Result(False, f"{name} isn't open.")
    for w in found:
        win.close(w.hwnd)
    return Result(True, f"Closed {name}.")


@tool("switch_to_app", "Bring an open app's window to the front.", {"name": "app name"})
async def switch_to_app(name: str) -> Result:
    found = await asyncio.to_thread(win.find_windows, name)
    if not found:
        return await open_app(name)
    await asyncio.to_thread(win.focus, found[0].hwnd)
    return Result(True, f"Here's {name}.")


@tool("window", "Minimize, maximize or restore an app's window.",
      {"name": "app name", "action": "minimize | maximize | restore"})
async def window(name: str, action: str) -> Result:
    found = await asyncio.to_thread(win.find_windows, name)
    if not found or action not in ("minimize", "maximize", "restore"):
        return Result(False, f"I couldn't find a {name} window.")
    win.show(found[0].hwnd, action)
    return Result(True, f"Done, {name} {action}d.")


@tool("type_text", "Type text into whatever is focused right now.", {"text": "text to type"})
async def type_text(text: str) -> Result:
    await asyncio.to_thread(win.leave_yashi)
    await asyncio.to_thread(win.type_text, text)
    return Result(True, "Typed it.")


@tool("press_keys", "Press a key or shortcut, e.g. 'enter', 'ctrl+t', 'alt+tab', 'ctrl+shift+esc'.",
      {"keys": "shortcut"})
async def press_keys(keys: str) -> Result:
    try:
        await asyncio.to_thread(win.leave_yashi)
        await asyncio.to_thread(win.press_keys, keys)
    except ValueError as error:
        return Result(False, f"I don't know that key: {error}.")
    return Result(True, "Done.")


@tool("media", "System media keys; work for any player (browser video, music app).",
      {"action": "play_pause | next | previous | stop"})
async def media(action: str) -> Result:
    if action not in ("play_pause", "next", "previous", "stop"):
        return Result(False, "I can play/pause, skip, go back or stop.")
    win.tap_vk(action)
    return Result(True, {"play_pause": "Done.", "next": "Skipped.", "previous": "Going back.",
                         "stop": "Stopped."}[action])


@tool("volume", "System volume.", {"action": "up | down | mute | set", "?level": "0-100, for set"})
async def volume(action: str, level: int = None) -> Result:
    if action == "set" and level is not None:
        await asyncio.to_thread(win.set_volume, level)
        return Result(True, f"Volume at {int(level)}.")
    if action in ("up", "down"):
        win.tap_vk(f"volume_{action}", 5)                 # 10%
        return Result(True, "Louder." if action == "up" else "Quieter.")
    if action == "mute":
        win.tap_vk("mute")
        return Result(True, "Toggled mute.")
    return Result(False, "I can turn it up, down, mute it or set a level.")


@tool("lock_pc", "Lock the computer.")
async def lock_pc() -> Result:
    win.lock()
    return Result(True, "Locked. See you in a bit.")


@tool("screenshot", "Take a screenshot and save it to Pictures.")
async def screenshot() -> Result:
    folder = Path.home() / "Pictures" / "Yashi Screenshots"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"screenshot-{datetime.now():%Y%m%d-%H%M%S}.png"
    ok = await asyncio.to_thread(win.screenshot, str(path))
    return Result(ok, f"Saved a screenshot to Pictures, {path.name}." if ok else "The screenshot failed.")


# ── Power: always asked first ────────────────────────────────────────────────
POWER = {
    "shutdown": (["shutdown", "/s", "/t", "15"], "shut down"),
    "restart": (["shutdown", "/r", "/t", "15"], "restart"),
    "sleep": (None, "go to sleep"),
}


async def _prepare_power(action: str):
    if action not in POWER:
        return Result(False, "I can shut down, restart or put the PC to sleep.")
    return f"Should I {POWER[action][1]} the PC now?", {"action": action}


@tool("power", "Shut down, restart or sleep the PC.", {"action": "shutdown | restart | sleep"},
      confirm=True, prepare=_prepare_power)
async def power(action: str) -> Result:
    command, verb = POWER[action]
    if command is None:
        asyncio.get_running_loop().call_later(2, win.sleep_pc)
        return Result(True, "Going to sleep. Night!")
    subprocess.run(command, creationflags=win.NO_WINDOW)
    return Result(True, f"Okay, the PC will {verb} in 15 seconds. Say cancel shutdown to stop it.")


@tool("cancel_shutdown", "Cancel a pending shutdown or restart.")
async def cancel_shutdown() -> Result:
    subprocess.run(["shutdown", "/a"], creationflags=win.NO_WINDOW)
    return Result(True, "Cancelled, we're staying on.")


@tool("current_time", "Tell the current date and time.")
async def current_time() -> Result:
    return Result(True, time.strftime("It's %I:%M %p, %A %d %B.").replace(" 0", " "))
