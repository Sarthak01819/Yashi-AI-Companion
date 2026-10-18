#!/usr/bin/env python3
"""
Yashi -- start everything with one command.

    python run.py              backend API (:8000) + the frontend (:5173)
    python run.py --api-only   backend API only

The frontend in frontend/ (Vite + React) is the only UI; the backend serves
the API and never a copy of the UI.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Must be set before uvicorn/logging starts so Windows terminal handles unicode
os.environ["PYTHONIOENCODING"] = "utf-8"
# The env var only affects child processes; reconfigure this one's streams too,
# otherwise the banner crashes on cp1252 consoles.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import uvicorn
from config.settings import HOST, PORT, LOG_LEVEL, FRONTEND_URL


def start_frontend():
    """Start the Vite dev server for frontend/ (installs packages on first run)."""
    frontend = ROOT / "frontend"
    npm = shutil.which("npm")
    if not npm:
        print("  [!] npm not found - install Node.js to run the frontend.\n")
        return None
    if not (frontend / "node_modules").exists():
        print("  Installing frontend packages (first run)...")
        subprocess.run([npm, "install"], cwd=frontend, check=False)
    return subprocess.Popen([npm, "run", "dev", "--", "--strictPort"], cwd=frontend)


def stop(process):
    """Stop the frontend and its child processes (npm -> node on Windows)."""
    if process is None or process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    else:
        process.terminate()


if __name__ == "__main__":
    api_only = "--api-only" in sys.argv[1:]

    print("╔══════════════════════════════════════╗")
    print("║       * YASHI -- AI Companion        ║")
    print("╚══════════════════════════════════════╝")
    print(f"\n  API:  http://localhost:{PORT}")
    if not api_only:
        print(f"  App:  {FRONTEND_URL}   <- open this")
    print()

    frontend = None if api_only else start_frontend()
    try:
        uvicorn.run(
            "app.main:app",
            host=HOST,
            port=PORT,
            reload=False,
            log_level=LOG_LEVEL.lower(),
            access_log=True,
        )
    finally:
        stop(frontend)
