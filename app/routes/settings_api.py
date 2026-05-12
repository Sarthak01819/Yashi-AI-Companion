"""
Settings API — lets the frontend toggle LLM and TTS backends at runtime.
"""
import json
import logging
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings")

SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "config" / "settings.py"


def _read_setting(key: str) -> str:
    """Read a setting value from settings.py."""
    for line in SETTINGS_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith(f"{key} ") or line.startswith(f"{key}="):
            # Extract value after = sign
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
            return val
    return ""


def _write_setting(key: str, value: str):
    """Patch a setting value in settings.py."""
    src = SETTINGS_FILE.read_text(encoding="utf-8")
    lines = src.splitlines()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if (stripped.startswith(f"{key} =") or
                stripped.startswith(f"{key}=")) and not stripped.startswith("#"):
            # preserve indentation
            indent = line[: len(line) - len(line.lstrip())]
            new_lines.append(f'{indent}{key} = "{value}"')
        else:
            new_lines.append(line)
    SETTINGS_FILE.write_text("\n".join(new_lines), encoding="utf-8")


@router.get("/current")
async def get_settings():
    """Return current LLM and TTS backend settings."""
    return {
        "llm_backend": _read_setting("LLM_BACKEND"),
        "tts_backend": _read_setting("TTS_BACKEND"),
    }


@router.post("/llm/{backend}")
async def set_llm_backend(backend: str):
    """Switch LLM backend: openai | ollama"""
    if backend not in ("openai", "ollama"):
        return JSONResponse({"error": "Invalid backend. Use 'openai' or 'ollama'"}, status_code=400)

    _write_setting("LLM_BACKEND", backend)

    # Hot-swap the engine's LLM client without restarting
    try:
        import importlib
        import core.conversation.engine as eng_mod
        import core.llm.openai_client as oc_mod
        import core.llm.ollama_client as ol_mod

        # Reset the singleton so next message picks up new backend
        oc_mod._client = None
        ol_mod._client_instance = None

        # Reload settings so the change takes effect immediately
        import config.settings as settings_mod
        importlib.reload(settings_mod)

        logger.info("LLM backend switched to: %s", backend)
        return {"success": True, "llm_backend": backend,
                "message": f"LLM switched to {backend.upper()}. Active on next message."}
    except Exception as e:
        logger.warning("Hot-swap failed: %s", e)
        return {"success": True, "llm_backend": backend,
                "message": f"LLM switched to {backend.upper()}. Restart for changes to take full effect."}


@router.post("/tts/{backend}")
async def set_tts_backend(backend: str):
    """Switch TTS backend: elevenlabs | browser | piper"""
    if backend not in ("elevenlabs", "browser", "piper"):
        return JSONResponse({"error": "Invalid backend"}, status_code=400)

    _write_setting("TTS_BACKEND", backend)

    try:
        import importlib
        import config.settings as settings_mod
        importlib.reload(settings_mod)
        import core.voice.elevenlabs_tts as tts_mod
        importlib.reload(tts_mod)
        logger.info("TTS backend switched to: %s", backend)
    except Exception as e:
        logger.warning("TTS hot-swap: %s", e)

    label = {"elevenlabs": "ElevenLabs AI Voice", "browser": "Browser Voice",
             "piper": "Piper (Local)"}.get(backend, backend)
    return {"success": True, "tts_backend": backend,
            "message": f"TTS switched to {label}. Active on next message."}