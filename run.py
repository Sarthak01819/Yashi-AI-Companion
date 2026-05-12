#!/usr/bin/env python3
"""
Yashi -- Main startup script.
Run with: python run.py
"""

import os
import sys
from pathlib import Path

# Must be set before uvicorn/logging starts so Windows terminal handles unicode
os.environ["PYTHONIOENCODING"] = "utf-8"

sys.path.insert(0, str(Path(__file__).parent))

import uvicorn
from config.settings import HOST, PORT, LOG_LEVEL

if __name__ == "__main__":
    print("╔══════════════════════════════════════╗")
    print("║       * YASHI -- AI Companion        ║")
    print("║    Local  Private  Emotionally       ║")
    print("║       Intelligent Companion          ║")
    print("╚══════════════════════════════════════╝")
    print(f"\n  Open in browser: http://localhost:{PORT}")
    print(f"  Make sure Ollama is running: ollama serve\n")

    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level=LOG_LEVEL.lower(),
        access_log=True,
    )
