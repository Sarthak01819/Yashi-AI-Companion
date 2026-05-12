#!/usr/bin/env python3
"""
Yashi Desktop Launcher
Run with: python desktop.py

Opens Yashi as a native desktop window using pywebview.
The FastAPI backend runs in a background thread.
OS-level actions (opening Spotify, files, folders) work reliably
because this is a native process, not a browser tab.

Install requirement: pip install pywebview
"""

import os
import sys
import time
import threading
import subprocess
from pathlib import Path

# ── Ensure we're in the right directory ───────────────────────────────────────
YASHI_DIR = Path(__file__).resolve().parent
os.chdir(YASHI_DIR)
sys.path.insert(0, str(YASHI_DIR))

# ── Load .env before anything else ────────────────────────────────────────────
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=YASHI_DIR / ".env")
except ImportError:
    pass

from config.settings import HOST, PORT


def start_server():
    """Start the FastAPI server in a background thread."""
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",   # localhost only — more secure for desktop app
        port=PORT,
        reload=False,
        log_level="warning",   # less noise in desktop mode
        access_log=False,
    )


def wait_for_server(timeout: int = 15) -> bool:
    """Wait until the server is accepting connections."""
    import urllib.request
    url = f"http://127.0.0.1:{PORT}/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url, timeout=1)
            return True
        except Exception:
            time.sleep(0.3)
    return False


def main():
    print("╔══════════════════════════════════════╗")
    print("║       * YASHI -- AI Companion        ║")
    print("║         Desktop Application          ║")
    print("╚══════════════════════════════════════╝")
    print()

    # Check pywebview
    try:
        import webview
    except ImportError:
        print("pywebview is not installed.")
        print("Run this to install it:")
        print()
        print("    pip install pywebview")
        print()
        input("Press Enter to exit...")
        sys.exit(1)

    # Start FastAPI in background thread
    print("Starting Yashi backend...")
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    if not wait_for_server(timeout=20):
        print("ERROR: Server did not start in time.")
        print("Check the terminal for errors above.")
        input("Press Enter to exit...")
        sys.exit(1)

    print("Yashi is ready! Opening window...")
    print()

    # Create the native window
    window = webview.create_window(
        title       = "Yashi — AI Companion",
        url         = f"http://127.0.0.1:{PORT}",
        width       = 1280,
        height      = 800,
        min_size    = (900, 600),
        resizable   = True,
        text_select = True,        # allow text selection
        confirm_close = False,     # don't ask on close
    )

    # Start the window (blocks until closed)
    webview.start(
        debug          = False,
        private_mode   = False,   # keep localStorage etc.
    )

    print("Yashi closed. Goodbye!")


if __name__ == "__main__":
    main()