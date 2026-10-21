"""
Yashi FastAPI Application Entry Point
"""

import os
import sys
import asyncio
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
from fastapi.responses import RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config.settings import LOGS_DIR, DATA_DIR, LOG_LEVEL, LOG_FILE, FRONTEND_URL
from core.memory.database import initialize_database
from core.llm.ollama_client import get_ollama_cloud_client
from core.llm.anthropic_client import get_anthropic_client
import config.settings as settings_mod
from plugins.plugin_loader import load_all_plugins

from app.routes.chat import router as chat_router
from app.routes.memory_api import router as memory_router
from app.routes.tts_serve import router as tts_router
from app.routes.settings_api import router as settings_router
from app.routes.stt_api import router as stt_router
from app.routes.profile_api import router as profile_router

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

# ── Lifespan ──────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 50)
    logger.info("  Yashi is starting up...")
    logger.info("=" * 50)

    initialize_database()

    from config.settings import TTS_BACKEND, ELEVENLABS_API_KEY

    await _choose_brain()

    if TTS_BACKEND == "elevenlabs":
        if not ELEVENLABS_API_KEY:
            logger.warning("ELEVENLABS_API_KEY not set — TTS will fall back to browser voice")
        else:
            logger.info("TTS backend: ElevenLabs")
    else:
        logger.info("TTS backend: %s", TTS_BACKEND)

    plugins = load_all_plugins()
    logger.info("Plugins loaded: %s", [p.name for p in plugins])
    logger.info("Yashi API ready. Open the app: %s", FRONTEND_URL)
    warmup = asyncio.create_task(_warm_up())
    yield
    warmup.cancel()
    for close in (get_anthropic_client().close, get_ollama_cloud_client().close):
        try:
            await close()
        except Exception:
            pass
    logger.info("Yashi shut down.")


async def _brain_ok(backend: str) -> tuple:
    """Can this cloud brain answer right now? Returns (ok, detail)."""
    if backend == "ollama_cloud":
        if not settings_mod.OLLAMA_API_KEY:
            return False, "OLLAMA_API_KEY is not set"
        return await get_ollama_cloud_client().verify()
    if backend == "anthropic":
        return await get_anthropic_client().verify()
    if backend == "openai":
        ok = bool(settings_mod.OPENAI_API_KEY)
        return ok, settings_mod.OPENAI_MODEL if ok else "OPENAI_API_KEY is not set"
    return False, f"unknown backend '{backend}'"


async def _choose_brain() -> None:
    """Keep the configured brain if it works, else switch to the first one that does."""
    from core.conversation.engine import configured_backends

    active = settings_mod.LLM_BACKEND
    ok, detail = await _brain_ok(active)
    if ok:
        logger.info("LLM backend: %s (%s)", active, detail)
        return
    logger.error("LLM backend '%s' is not usable: %s", active, detail)
    for backend in configured_backends():
        if backend == active:
            continue
        ok, detail = await _brain_ok(backend)
        if ok:
            settings_mod.LLM_BACKEND = backend
            logger.warning("Using '%s' (%s) instead. Switch back in Settings once '%s' works.",
                           backend, detail, active)
            return
        logger.warning("'%s' is not usable either: %s", backend, detail)
    logger.error("No working AI brain. Add a valid key to .env "
                 "(OLLAMA_API_KEY, ANTHROPIC_API_KEY or OPENAI_API_KEY).")


async def _warm_up():
    """Load the on-device models (sentiment, embeddings, Whisper) in the background."""
    loop = asyncio.get_running_loop()
    try:
        from core.emotion.text_sentiment import analyse_sentiment
        from core.memory.semantic_memory import search_memory
        await loop.run_in_executor(None, analyse_sentiment, "hello")
        await loop.run_in_executor(None, search_memory, "hello")
        logger.info("Warm-up: sentiment + embedding models ready")
        from core.voice.stt import _get_model as _load_whisper
        await loop.run_in_executor(None, _load_whisper)
        logger.info("Warm-up: Whisper speech-to-text ready")
    except Exception as e:
        logger.warning("Warm-up (local models) failed: %s", e)


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Yashi", version="1.0.0", lifespan=lifespan)

# Only the Yashi frontend may call the API. A wildcard here would let any
# website you visit drive Yashi from your browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://127.0.0.1:5173",   # vite dev
        "http://localhost:4173", "http://127.0.0.1:4173",   # vite preview
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(memory_router)
app.include_router(tts_router)
app.include_router(settings_router)
app.include_router(stt_router)
app.include_router(profile_router)


# The backend is API-only; the one and only UI is the Vite app in frontend/.
@app.get("/", include_in_schema=False)
async def index():
    return RedirectResponse(FRONTEND_URL)


@app.get("/health")
async def health():
    import config.settings as s
    info = {
        "status": "ok",
        "llm_backend": s.LLM_BACKEND,
        "llm_model": {
            "ollama_cloud": s.OLLAMA_CLOUD_MODEL,
            "anthropic": s.ANTHROPIC_MODEL,
            "openai":    s.OPENAI_MODEL,
        }.get(s.LLM_BACKEND, "unknown"),
        "tts_backend": s.TTS_BACKEND,
        "ollama_cloud_key_set": bool(s.OLLAMA_API_KEY),
        "anthropic_key_set": bool(s.ANTHROPIC_API_KEY),
        "openai_key_set": bool(s.OPENAI_API_KEY),
        "elevenlabs_key_set": bool(s.ELEVENLABS_API_KEY),
    }
    return info