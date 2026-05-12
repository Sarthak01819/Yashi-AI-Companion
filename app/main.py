"""
Yashi FastAPI Application Entry Point
"""

import os
import sys
import logging
from pathlib import Path

# Fix Windows terminal unicode issues before anything else
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Load .env file BEFORE importing anything from config.settings
# This ensures OPENAI_API_KEY and ELEVENLABS_API_KEY are available
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parent.parent / ".env"
    load_dotenv(dotenv_path=_env_path)
    if _env_path.exists():
        pass  # loaded
    else:
        print(f"[Yashi] WARNING: No .env file found at {_env_path}")
        print("[Yashi] Create it with OPENAI_API_KEY=sk-... and ELEVENLABS_API_KEY=...")
except ImportError:
    print("[Yashi] WARNING: python-dotenv not installed. Run: pip install python-dotenv")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config.settings import BASE_DIR, LOGS_DIR, DATA_DIR, LOG_LEVEL, LOG_FILE
from core.memory.database import initialize_database
from core.llm.model_router import set_available_models
from core.llm.ollama_client import get_ollama_client
from plugins.plugin_loader import load_all_plugins

from app.routes.chat import router as chat_router
from app.routes.audio import router as audio_router
from app.routes.memory_api import router as memory_router
from app.routes.tts_serve import router as tts_router
from app.routes.voice import router as voice_router
from app.routes.settings_api import router as settings_router

# ── Logging ───────────────────────────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)

_fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

_console = logging.StreamHandler(sys.stdout)
_console.setFormatter(_fmt)

_file = logging.FileHandler(str(LOG_FILE), encoding="utf-8")
_file.setFormatter(_fmt)

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[_console, _file],
)
logger = logging.getLogger("yashi.main")

# ── Constants ─────────────────────────────────────────────────────────────────
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"

MIME_TYPES = {
    ".html": "text/html",
    ".css":  "text/css",
    ".js":   "application/javascript",
    ".json": "application/json",
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
    ".wav":  "audio/wav",
    ".mp3":  "audio/mpeg",
    ".mp4":  "video/mp4",
    ".woff2":"font/woff2",
    ".woff": "font/woff",
    ".ttf":  "font/ttf",
}


# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("  Yashi is starting up...")
    logger.info("=" * 50)

    initialize_database()

    from config.settings import LLM_BACKEND, OPENAI_API_KEY, TTS_BACKEND, ELEVENLABS_API_KEY

    if LLM_BACKEND == "openai":
        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY is not set! Create a .env file with OPENAI_API_KEY=sk-...")
        else:
            logger.info("LLM backend: OpenAI (%s)", OPENAI_API_KEY[:8] + "...")
        client = None
    else:
        client = get_ollama_client()
        if await client.is_available():
            models = await client.list_models()
            set_available_models(models)
            logger.info("Ollama connected. Models: %s", models)
        else:
            logger.warning("Ollama not reachable.")

    if TTS_BACKEND == "elevenlabs":
        if not ELEVENLABS_API_KEY:
            logger.warning("ELEVENLABS_API_KEY not set — TTS will fall back to browser voice")
        else:
            logger.info("TTS backend: ElevenLabs")
    else:
        logger.info("TTS backend: %s", TTS_BACKEND)

    plugins = load_all_plugins()
    logger.info("Plugins loaded: %s", [p.name for p in plugins])
    logger.info("Yashi ready -> http://localhost:8000")
    yield
    if client:
        await client.close()
    logger.info("Yashi shut down.")


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Yashi", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(audio_router)
app.include_router(memory_router)
app.include_router(tts_router)
app.include_router(voice_router)
app.include_router(settings_router)


@app.get("/")
async def index():
    index_file = FRONTEND_DIST_DIR / "index.html"
    if not index_file.exists():
        return Response(
            content="Frontend build not found. Run `npm run build` in the frontend directory.",
            status_code=503,
        )
    return FileResponse(str(index_file), media_type="text/html")


@app.get("/assets/{filepath:path}")
async def frontend_assets(filepath: str):
    full_path = FRONTEND_DIST_DIR / "assets" / filepath
    if not full_path.exists() or not full_path.is_file():
        return Response(content=f"Not found: {filepath}", status_code=404)
    media_type = MIME_TYPES.get(full_path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(full_path), media_type=media_type)


@app.get("/static/{filepath:path}")
async def static_files(filepath: str):
    suffix = ("." + filepath.rsplit(".", 1)[-1].lower()) if "." in filepath else ""
    for search_dir in [
        FRONTEND_DIR / "assets",
        DATA_DIR,
        FRONTEND_DIR / "public",
        FRONTEND_DIR,
    ]:
        full_path = search_dir / filepath
        if full_path.exists() and full_path.is_file():
            media_type = MIME_TYPES.get(suffix, "application/octet-stream")
            return FileResponse(str(full_path), media_type=media_type)
    return Response(content=f"Not found: {filepath}", status_code=404)


@app.get("/static/yashi-avatar.mp4")
async def serve_avatar_video():
    """Serve the avatar video file."""
    for search_path in [
        BASE_DIR / "data" / "yashi-avatar.mp4",
        BASE_DIR / "frontend" / "assets" / "yashi-avatar.mp4",
        BASE_DIR / "frontend" / "public" / "yashi-avatar.mp4",
    ]:
        if search_path.exists():
            return FileResponse(str(search_path), media_type="video/mp4")
    return Response(content="Avatar video not found. Copy yashi-avatar.mp4 to data/", status_code=404)


@app.get("/health")
async def health():
    from config.settings import LLM_BACKEND, OPENAI_API_KEY, TTS_BACKEND, ELEVENLABS_API_KEY
    info = {
        "status": "ok",
        "llm_backend": LLM_BACKEND,
        "tts_backend": TTS_BACKEND,
        "openai_key_set": bool(OPENAI_API_KEY),
        "elevenlabs_key_set": bool(ELEVENLABS_API_KEY),
    }
    if LLM_BACKEND == "ollama":
        client = get_ollama_client()
        info["ollama"] = await client.is_available()
    return info