#!/usr/bin/env python3
"""
Add Yashi to the Desktop and the Start Menu, like an installed app.

    python tools/make_shortcut.py

The shortcut runs desktop.py with this project's pythonw.exe (no console
window) and uses assets/yashi.ico, which is drawn here if it is missing.
"""

import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICON = ROOT / "assets" / "yashi.ico"


# ── Icon: a crimson disc with a white heart, drawn without any image library ──
def _heart(x: float, y: float) -> float:
    """<= 0 inside the heart. x, y in [-1.5, 1.5], y pointing up."""
    return (x * x + y * y - 1) ** 3 - x * x * y ** 3


def _pixels(size: int) -> bytes:
    rows = []
    ss = 4                                   # 4x4 supersampling for smooth edges
    for py in range(size):
        row = bytearray([0])                 # PNG filter byte
        for px in range(size):
            disc = heart = 0
            for sy in range(ss):
                for sx in range(ss):
                    u = (px + (sx + 0.5) / ss) / size * 2 - 1
                    v = (py + (sy + 0.5) / ss) / size * 2 - 1
                    if u * u + v * v <= 0.96:
                        disc += 1
                        if _heart(u * 1.85, -(v * 1.85) + 0.25) <= 0:
                            heart += 1
            n = ss * ss
            a = disc / n
            h = heart / max(disc, 1)
            # crimson -> white where the heart is
            r = round(200 + (255 - 200) * h)
            g = round(16 + (255 - 16) * h)
            b = round(46 + (255 - 46) * h)
            row += bytes((r, g, b, round(a * 255)))
        rows.append(bytes(row))
    return b"".join(rows)


def _png(size: int) -> bytes:
    def chunk(kind, data):
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)
    header = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header)
            + chunk(b"IDAT", zlib.compress(_pixels(size), 9)) + chunk(b"IEND", b""))


def make_icon(path: Path = ICON) -> Path:
    sizes = [16, 32, 48, 256]
    images = [_png(s) for s in sizes]
    out = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    for size, data in zip(sizes, images):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(out + b"".join(images))
    return path


# ── Shortcuts ────────────────────────────────────────────────────────────────
def make_shortcut(link: Path, target: Path, args: str, icon: Path) -> None:
    def q(value):                             # PowerShell single-quoted literal
        return "'" + str(value).replace("'", "''") + "'"
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + q(link) + ");"
        f"$s.TargetPath = {q(target)}; $s.Arguments = {q(args)};"
        f"$s.WorkingDirectory = {q(ROOT)}; $s.IconLocation = {q(icon)};"
        "$s.Description = 'Yashi - AI Companion'; $s.Save()"
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True)


APP_ID = "Yashi.AICompanion"          # must match desktop.py


def set_shortcut_app_id(link: Path, app_id: str = APP_ID) -> None:
    """
    Stamp the shortcut with Yashi's AppUserModelID (the same one desktop.py
    sets on its process), so the running window and the pinned shortcut share
    one taskbar button with the Yashi icon. Done through the shell's
    IPropertyStore; there is no PowerShell cmdlet for it.
    """
    import ctypes
    from ctypes import POINTER, byref, c_void_p, c_wchar_p, c_ulong, c_ushort, Structure, WINFUNCTYPE, HRESULT

    class GUID(Structure):
        _fields_ = [("d1", c_ulong), ("d2", c_ushort), ("d3", c_ushort), ("d4", ctypes.c_ubyte * 8)]

    def guid(text):
        import uuid
        u = uuid.UUID(text)
        return GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))

    class PROPERTYKEY(Structure):
        _fields_ = [("fmtid", GUID), ("pid", c_ulong)]

    class PROPVARIANT(Structure):
        _fields_ = [("vt", c_ushort), ("r1", c_ushort), ("r2", c_ushort), ("r3", c_ushort),
                    ("pwszVal", c_wchar_p), ("pad", c_void_p)]

    ole32, shell32 = ctypes.windll.ole32, ctypes.windll.shell32
    ole32.CoInitialize(None)
    store = c_void_p()
    iid_store = guid("886d8eeb-8cf2-4446-8d02-cdba1dbdcf99")         # IPropertyStore
    shell32.SHGetPropertyStoreFromParsingName.argtypes = (c_wchar_p, c_void_p, ctypes.c_int,
                                                          POINTER(GUID), POINTER(c_void_p))
    hr = shell32.SHGetPropertyStoreFromParsingName(str(link), None, 2, byref(iid_store), byref(store))
    if hr != 0:
        raise OSError(f"SHGetPropertyStoreFromParsingName failed: {hr:#x}")
    vtable = ctypes.cast(ctypes.cast(store, POINTER(c_void_p))[0], POINTER(c_void_p))
    set_value = WINFUNCTYPE(HRESULT, c_void_p, POINTER(PROPERTYKEY), POINTER(PROPVARIANT))(vtable[6])
    commit = WINFUNCTYPE(HRESULT, c_void_p)(vtable[7])
    release = WINFUNCTYPE(c_ulong, c_void_p)(vtable[2])
    key = PROPERTYKEY(guid("9f4c2855-9f79-4b39-a8d0-e1d42de1d5f3"), 5)  # System.AppUserModel.ID
    value = PROPVARIANT(vt=31, pwszVal=app_id)                       # VT_LPWSTR
    try:
        set_value(store, byref(key), byref(value))
        commit(store)
    finally:
        release(store)


def main():
    if os.name != "nt":
        sys.exit("Shortcuts are only made on Windows.")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if not pythonw.exists():
        sys.exit(f"pythonw.exe not found next to {sys.executable}")
    icon = ICON if ICON.exists() else make_icon()

    desktop = Path(subprocess.run(
        ["powershell", "-NoProfile", "-Command", "[Environment]::GetFolderPath('Desktop')"],
        capture_output=True, text=True, check=True).stdout.strip())
    start_menu = Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    args = f'"{ROOT / "desktop.py"}"'
    for folder in (desktop, start_menu):
        link = folder / "Yashi.lnk"
        make_shortcut(link, pythonw, args, icon)
        set_shortcut_app_id(link)
        print("Created", link)


if __name__ == "__main__":
    if "--icon-only" in sys.argv:
        print("Wrote", make_icon())
    else:
        main()
