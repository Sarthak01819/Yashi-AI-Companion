"""
Settings API — brain/voice switching, API keys and provider tests.

The switch is applied two ways:
  1. on the live `config.settings` module object, so it takes effect on the very
     next message (the engine and the TTS layer read these attributes lazily);
  2. persisted back into config/settings.py so it survives a restart.
"""
import logging
import re
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

import config.settings as settings
from app.security import require_app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/settings")

ROOT = Path(__file__).resolve().parent.parent.parent
SETTINGS_FILE = ROOT / "config" / "settings.py"
ENV_FILE = ROOT / ".env"

# Values editable from the dashboard. Secrets are never sent back unmasked.
SECRET_KEYS = ("OLLAMA_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "ELEVENLABS_API_KEY")
PLAIN_KEYS = ("OLLAMA_CLOUD_MODEL", "ANTHROPIC_MODEL", "OPENAI_MODEL",
              "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL")

LLM_BACKENDS = ("ollama_cloud", "anthropic", "openai")
TTS_BACKENDS = ("elevenlabs", "browser")

LLM_LABELS = {
    "ollama_cloud": "Ollama Cloud",
    "anthropic": "Claude",
    "openai":    "OpenAI",
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


@router.post("/llm/{backend}", dependencies=[Depends(require_app)])
async def set_llm_backend(backend: str):
    """Switch LLM backend: ollama_cloud | anthropic | openai"""
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


@router.post("/tts/{backend}", dependencies=[Depends(require_app)])
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


# ── API keys ─────────────────────────────────────────────────────────────────
def _mask(value: str) -> str:
    return f"••••{value[-4:]}" if len(value) > 8 else ("••••" if value else "")


def _write_env(updates: dict) -> None:
    """Update or append KEY=value lines in .env, keeping everything else."""
    lines = ENV_FILE.read_text(encoding="utf-8").splitlines() if ENV_FILE.exists() else []
    remaining = dict(updates)
    for i, line in enumerate(lines):
        match = re.match(r"\s*([A-Z_][A-Z0-9_]*)\s*=", line)
        if match and match.group(1) in remaining:
            lines[i] = f"{match.group(1)}={remaining.pop(match.group(1))}"
    lines += [f"{key}={value}" for key, value in remaining.items()]
    ENV_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def reset_clients() -> None:
    """Drop cached API clients so the next request uses the new keys/models."""
    import core.llm.anthropic_client as anthropic_client
    import core.llm.ollama_client as ollama_client
    import core.llm.openai_client as openai_client
    import core.voice.elevenlabs_tts as elevenlabs_tts
    anthropic_client._client = None
    openai_client._client = None
    ollama_client._instance = None
    elevenlabs_tts._client = None


@router.get("/keys")
async def get_keys():
    return {
        "secrets": {k: {"set": bool(getattr(settings, k, "")), "masked": _mask(getattr(settings, k, ""))}
                    for k in SECRET_KEYS},
        "values": {k: getattr(settings, k, "") for k in PLAIN_KEYS},
    }


class KeyUpdate(BaseModel):
    values: dict


@router.put("/keys", dependencies=[Depends(require_app)])
async def put_keys(update: KeyUpdate):
    allowed = set(SECRET_KEYS) | set(PLAIN_KEYS)
    clean = {}
    for key, value in update.values.items():
        if key not in allowed or not isinstance(value, str):
            continue
        value = value.strip()
        if "\n" in value or "\r" in value or len(value) > 300:
            return JSONResponse({"error": f"Invalid value for {key}"}, status_code=400)
        if key in PLAIN_KEYS and not value:
            continue                              # keep the default model / voice
        clean[key] = value
    if not clean:
        return JSONResponse({"error": "Nothing to update"}, status_code=400)
    _write_env(clean)
    for key, value in clean.items():
        setattr(settings, key, value)
    reset_clients()
    logger.info("Updated settings from dashboard: %s", ", ".join(sorted(clean)))
    return {"success": True, "updated": sorted(clean), **(await get_keys())}


@router.post("/test/{provider}", dependencies=[Depends(require_app)])
async def test_provider(provider: str):
    """Live check of one provider with the current key. Returns {ok, detail}."""
    try:
        if provider == "ollama_cloud":
            if not settings.OLLAMA_API_KEY:
                return {"ok": False, "detail": "No key set"}
            from core.llm.ollama_client import get_ollama_cloud_client
            ok, detail = await get_ollama_cloud_client().verify()
        elif provider == "anthropic":
            from core.llm.anthropic_client import get_anthropic_client
            ok, detail = await get_anthropic_client().verify()
        elif provider == "openai":
            if not settings.OPENAI_API_KEY:
                return {"ok": False, "detail": "No key set"}
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                    json={"model": settings.OPENAI_MODEL, "max_tokens": 1,
                          "messages": [{"role": "user", "content": "hi"}]},
                )
            ok = r.status_code == 200
            detail = settings.OPENAI_MODEL if ok else (
                "No credit left" if "insufficient_quota" in r.text else
                "Key rejected" if r.status_code == 401 else f"HTTP {r.status_code}")
        elif provider == "elevenlabs":
            if not settings.ELEVENLABS_API_KEY:
                return {"ok": False, "detail": "No key set"}
            async with httpx.AsyncClient(timeout=20) as client:
                r = await client.get("https://api.elevenlabs.io/v1/user/subscription",
                                     headers={"xi-api-key": settings.ELEVENLABS_API_KEY})
            ok = r.status_code == 200
            if ok:
                d = r.json()
                detail = f"{d.get('character_count', 0):,} / {d.get('character_limit', 0):,} characters used"
            else:
                detail = "Key rejected" if r.status_code == 401 else f"HTTP {r.status_code}"
        else:
            return JSONResponse({"error": "Unknown provider"}, status_code=400)
    except Exception as e:                                   # network etc.
        ok, detail = False, f"{type(e).__name__}"
    return {"ok": bool(ok), "detail": detail}


@router.get("/ollama-models")
async def ollama_models():
    """Models available to the configured Ollama Cloud key (for the model picker)."""
    if not settings.OLLAMA_API_KEY:
        return {"models": []}
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{settings.OLLAMA_CLOUD_URL}/api/tags",
                                 headers={"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"})
        r.raise_for_status()
        return {"models": sorted(m.get("name", "") for m in r.json().get("models", []))}
    except Exception:
        return {"models": []}
