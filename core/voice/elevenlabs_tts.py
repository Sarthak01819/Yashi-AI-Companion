"""
ElevenLabs TTS — human-quality AI voice synthesis.
Free tier: 10,000 characters/month.
Falls back to browser TTS if API key is missing or quota exceeded.
"""

import hashlib
import logging
import asyncio
import re
from pathlib import Path
from typing import Optional

import httpx

import config.settings as settings


def _tts_setting() -> str:
    """Read TTS_BACKEND at call time so the sidebar toggle applies live."""
    return getattr(settings, "TTS_BACKEND", "browser")

logger = logging.getLogger(__name__)

# Emotion → slight stability/similarity/speed tweaks for expressive but natural delivery
EMOTION_PARAMS = {
    "distressed": {"stability": 0.38, "similarity_boost": 0.80, "style": 0.26, "speed": 0.98},
    "sad":        {"stability": 0.42, "similarity_boost": 0.78, "style": 0.22, "speed": 0.99},
    "happy":      {"stability": 0.46, "similarity_boost": 0.77, "style": 0.28, "speed": 1.05},
    "joyful":     {"stability": 0.43, "similarity_boost": 0.75, "style": 0.32, "speed": 1.06},
    "excited":    {"stability": 0.40, "similarity_boost": 0.74, "style": 0.34, "speed": 1.08},
    "neutral":    {"stability": 0.48, "similarity_boost": 0.77, "style": 0.20, "speed": 1.04},
    "content":    {"stability": 0.50, "similarity_boost": 0.77, "style": 0.18, "speed": 1.03},
    "concerned":  {"stability": 0.45, "similarity_boost": 0.79, "style": 0.22, "speed": 1.00},
}

_client: Optional[httpx.AsyncClient] = None
_semaphore: Optional[asyncio.Semaphore] = None

MAX_CONCURRENT = 2      # ElevenLabs free-plan concurrency limit
MAX_ATTEMPTS = 4


def _slots() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    return _semaphore

def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={
                "xi-api-key":    settings.ELEVENLABS_API_KEY,
                "Content-Type":  "application/json",
                "Accept":        "audio/mpeg",
            },
            timeout=30,
        )
    return _client


def _cache_path(text: str, emotion: str) -> Path:
    h = hashlib.sha1(f"{text}|{emotion}|{settings.ELEVENLABS_VOICE_ID}".encode()).hexdigest()[:18]
    return Path(settings.ELEVENLABS_OUTPUT_DIR) / f"el_{h}.mp3"


def _normalise_tts_text(text: str) -> str:
    """Clean punctuation/markdown to avoid overlong pauses in generated speech."""
    t = text.strip()
    if not t:
        return ""

    t = re.sub(r"[`*_#~]", "", t)
    t = re.sub(r"\.{3,}", ".", t)
    t = re.sub(r"[,:;]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


async def synthesise_elevenlabs(text: str, emotion: str = "neutral") -> Optional[Path]:
    """
    Synthesise text with ElevenLabs. Returns path to MP3 or None on failure.
    """
    cleaned_text = _normalise_tts_text(text)
    if not settings.ELEVENLABS_API_KEY or not cleaned_text:
        return None

    Path(settings.ELEVENLABS_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    out = _cache_path(cleaned_text, emotion)
    if out.exists():
        return out

    params = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["neutral"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{settings.ELEVENLABS_VOICE_ID}"
    payload = {
        "text":       cleaned_text,
        "model_id":   settings.ELEVENLABS_MODEL,
        "voice_settings": {
            "stability":        min(1.0, max(0.0, (settings.ELEVENLABS_STABILITY + params["stability"]) / 2.0)),
            "similarity_boost": min(1.0, max(0.0, (settings.ELEVENLABS_SIMILARITY + params["similarity_boost"]) / 2.0)),
            "style":            params.get("style", 0.20),
            "speed":            params.get("speed", 1.04),
            "use_speaker_boost": True,
        },
    }

    # The free ElevenLabs plan allows 2 concurrent requests. A reply is
    # synthesised sentence-by-sentence in parallel, so without this limit the
    # 3rd+ sentence gets HTTP 429 and falls back to the robotic browser voice.
    async with _slots():
        client = _get_client()
        for attempt in range(MAX_ATTEMPTS):
            try:
                resp = await client.post(url, json=payload)
            except Exception as e:
                logger.warning("ElevenLabs request failed: %s", e)
                return None

            if resp.status_code == 200:
                out.write_bytes(resp.content)
                return out
            if resp.status_code == 401:
                logger.error("ElevenLabs: invalid API key")
                return None
            if resp.status_code == 429 and attempt < MAX_ATTEMPTS - 1:
                # Usually a concurrency blip: retry soon rather than waiting long.
                delay = min(float(resp.headers.get("retry-after", 0) or 0) or 0.6 * (attempt + 1), 3.0)
                logger.info("ElevenLabs busy (429) — retrying in %.1fs", delay)
                await asyncio.sleep(delay)
                continue

            logger.warning("ElevenLabs: HTTP %s — using browser voice for this sentence",
                           resp.status_code)
            return None
    return None


async def synthesise(text: str, emotion: str = "neutral") -> Optional[Path]:
    """Unified synthesise — picks backend from settings."""
    backend = _tts_setting()
    if backend == "elevenlabs":
        return await synthesise_elevenlabs(text, emotion)
    return None


def tts_backend() -> str:
    """The backend actually usable right now (falls back to browser speech)."""
    backend = _tts_setting()
    if backend == "elevenlabs" and settings.ELEVENLABS_API_KEY:
        return "elevenlabs"
    return "browser"
