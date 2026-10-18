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
from core.llm.model_router import set_available_models
from core.llm.ollama_client import get_ollama_client
from core.llm.anthropic_client import get_anthropic_client
import config.settings as settings_mod
from plugins.plugin_loader import load_all_plugins

from app.routes.chat import router as chat_router
from app.routes.memory_api import router as memory_router
from app.routes.tts_serve import router as tts_router
from app.routes.settings_api import router as settings_router
from app.routes.stt_api import router as stt_router

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

    from config.settings import (
        LLM_BACKEND, OPENAI_API_KEY, TTS_BACKEND, ELEVENLABS_API_KEY,
    )

    client = get_ollama_client()
    ollama_models = []
    if await client.is_available():
        ollama_models = await client.list_models()
        set_available_models(ollama_models)
        if ollama_models:
            logger.info("Ollama connected. Models: %s", ollama_models)
        else:
            logger.warning("Ollama is running but has no models. Run: ollama pull phi3:mini")

    if LLM_BACKEND == "ollama_cloud":
        from core.llm.ollama_client import get_ollama_cloud_client
        ok, detail = await get_ollama_cloud_client().verify()
        if ok:
            logger.info("LLM backend: Ollama Cloud (%s); local fallback: %s",
                        detail, settings_mod.DEFAULT_MODEL if ollama_models else "none")
        else:
            logger.error("Ollama Cloud is not usable: %s", detail)
            if ollama_models:
                settings_mod.LLM_BACKEND = "ollama"
                logger.warning("Falling back to local Ollama (%s).", settings_mod.DEFAULT_MODEL)
            else:
                logger.error("No local model either. Run: ollama pull llama3.2:3b")
    elif LLM_BACKEND == "anthropic":
        ok, detail = await get_anthropic_client().verify()
        if ok:
            logger.info("LLM backend: Anthropic %s", detail)
        else:
            logger.error("Anthropic is not usable: %s", detail)
            logger.error("Fix it by putting a working key in .env as ANTHROPIC_API_KEY=sk-ant-...")
            fallback = ("openai" if OPENAI_API_KEY else
                        "ollama" if ollama_models else None)
            if fallback:
                settings_mod.LLM_BACKEND = fallback
                logger.warning("Falling back to '%s' so Yashi can still answer. "
                               "Switch back to Claude from the sidebar once the key works.",
                               fallback)
            else:
                logger.error("No usable LLM backend! Add a valid API key or run: ollama pull phi3:mini")
    elif LLM_BACKEND == "openai":
        if not OPENAI_API_KEY:
            logger.error("OPENAI_API_KEY is not set! Create a .env file with OPENAI_API_KEY=sk-...")
        else:
            logger.info("LLM backend: OpenAI (%s)", OPENAI_API_KEY[:8] + "...")
    elif not ollama_models:
        logger.error("LLM backend is 'ollama' but no models are installed. Run: ollama pull phi3:mini")

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
    if client:
        await client.close()
    try:
        await get_anthropic_client().close()
        from core.llm.ollama_client import get_ollama_cloud_client
        await get_ollama_cloud_client().close()
    except Exception:
        pass
    logger.info("Yashi shut down.")


async def _warm_up():
    """Load the heavy models in the background so the first reply isn't slow."""
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
    if settings_mod.LLM_BACKEND == "ollama":
        try:
            from core.llm.model_router import select_model
            r = await get_ollama_client()._client.post(
                "/api/generate",
                json={"model": select_model("standard"), "keep_alive": "30m",
                      "options": {"num_ctx": 4096}},  # must match chat requests
                timeout=300,
            )
            logger.info("Warm-up: Ollama model loaded (%s)", r.status_code)
        except Exception as e:
            logger.warning("Warm-up (Ollama) failed: %s", e)


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
        }.get(s.LLM_BACKEND, s.DEFAULT_MODEL),
        "tts_backend": s.TTS_BACKEND,
        "ollama_cloud_key_set": bool(s.OLLAMA_API_KEY),
        "anthropic_key_set": bool(s.ANTHROPIC_API_KEY),
        "openai_key_set": bool(s.OPENAI_API_KEY),
        "elevenlabs_key_set": bool(s.ELEVENLABS_API_KEY),
    }
    if s.LLM_BACKEND == "ollama":
        client = get_ollama_client()
        info["ollama"] = await client.is_available()
    return info