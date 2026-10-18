"""
Settings API — lets the frontend toggle LLM and TTS backends at runtime.

The switch is applied two ways:
  1. on the live `config.settings` module object, so it takes effect on the very
     next message (the engine and the TTS layer read these attributes lazily);
  2. persisted back into config/settings.py so it survives a restart.
"""
import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import JSONResponse

import config.settings as settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings")

SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "settings.py"

LLM_BACKENDS = ("ollama_cloud", "ollama", "anthropic", "openai")
TTS_BACKENDS = ("elevenlabs", "browser")

LLM_LABELS = {
    "ollama_cloud": "Ollama Cloud",
    "anthropic": "Claude",
    "openai":    "OpenAI",
    "ollama":    "Ollama",
}
TTS_LABELS = {
    "elevenlabs": "ElevenLabs AI Voice",
    "browser":    "Browser Voice",
}


def _write_setting(key: str, value: str) -> None:
    """Patch a top-level string setting in settings.py (best effort)."""
    try:
        src = SETTINGS_FILE.read_text(encoding="utf-8")
        out, patched = [], False
        for line in src.splitlines():
            stripped = line.strip()
            if not patched and not stripped.startswith("#") and (
                stripped.startswith(f"{key} =") or stripped.startswith(f"{key}=")
            ):
                indent = line[: len(line) - len(line.lstrip())]
                out.append(f'{indent}{key} = "{value}"')
                patched = True
            else:
                out.append(line)
        if patched:
            SETTINGS_FILE.write_text("\n".join(out) + "\n", encoding="utf-8")
    except Exception as e:                      # persistence is a nice-to-have
        logger.warning("Could not persist %s: %s", key, e)


def _apply(key: str, value: str) -> None:
    setattr(settings, key, value)               # live — next message uses it
    _write_setting(key, value)                  # durable — survives restart


@router.get("/current")
async def get_settings():
    """Return current LLM and TTS backend settings + which keys are configured."""
    return {
        "llm_backend": getattr(settings, "LLM_BACKEND", "anthropic"),
        "tts_backend": getattr(settings, "TTS_BACKEND", "browser"),
        "available": {
            "ollama_cloud": bool(settings.OLLAMA_API_KEY),
            "anthropic":  bool(settings.ANTHROPIC_API_KEY),
            "openai":     bool(settings.OPENAI_API_KEY),
            "elevenlabs": bool(settings.ELEVENLABS_API_KEY),
        },
    }


@router.post("/llm/{backend}")
async def set_llm_backend(backend: str):
    """Switch LLM backend: ollama_cloud | ollama | anthropic | openai"""
    if backend not in LLM_BACKENDS:
        return JSONResponse(
            {"error": f"Invalid backend. Use one of {', '.join(LLM_BACKENDS)}"},
            status_code=400,
        )

    _apply("LLM_BACKEND", backend)
    logger.info("LLM backend switched to: %s", backend)

    label = LLM_LABELS.get(backend, backend)
    warning = ""
    if backend == "anthropic" and not settings.ANTHROPIC_API_KEY:
        warning = " (no ANTHROPIC_API_KEY in .env yet)"
    if backend == "ollama_cloud" and not settings.OLLAMA_API_KEY:
        warning = " (no OLLAMA_API_KEY in .env yet)"
    if backend == "openai" and not settings.OPENAI_API_KEY:
        warning = " (no OPENAI_API_KEY in .env yet)"

    return {
        "success": True,
        "llm_backend": backend,
        "message": f"Brain switched to {label}. Active on your next message.{warning}",
    }


@router.post("/tts/{backend}")
async def set_tts_backend(backend: str):
    """Switch TTS backend: elevenlabs | browser"""
    if backend not in TTS_BACKENDS:
        return JSONResponse({"error": "Invalid backend"}, status_code=400)

    _apply("TTS_BACKEND", backend)
    logger.info("TTS backend switched to: %s", backend)

    label = TTS_LABELS.get(backend, backend)
    warning = ""
    if backend == "elevenlabs" and not settings.ELEVENLABS_API_KEY:
        warning = " (no ELEVENLABS_API_KEY in .env — falling back to browser voice)"

    return {
        "success": True,
        "tts_backend": backend,
        "message": f"Voice switched to {label}. Active on your next message.{warning}",
    }
