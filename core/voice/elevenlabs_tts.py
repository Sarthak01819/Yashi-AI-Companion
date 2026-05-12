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

from config.settings import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL,
    ELEVENLABS_STABILITY,
    ELEVENLABS_SIMILARITY,
    ELEVENLABS_OUTPUT_DIR,
    TTS_BACKEND,
)

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

def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            headers={
                "xi-api-key":    ELEVENLABS_API_KEY,
                "Content-Type":  "application/json",
                "Accept":        "audio/mpeg",
            },
            timeout=30,
        )
    return _client


def _cache_path(text: str, emotion: str) -> Path:
    h = hashlib.sha1(f"{text}|{emotion}|{ELEVENLABS_VOICE_ID}".encode()).hexdigest()[:18]
    return Path(ELEVENLABS_OUTPUT_DIR) / f"el_{h}.mp3"


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
    if not ELEVENLABS_API_KEY or not cleaned_text:
        return None

    Path(ELEVENLABS_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)

    out = _cache_path(cleaned_text, emotion)
    if out.exists():
        return out

    params = EMOTION_PARAMS.get(emotion, EMOTION_PARAMS["neutral"])
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{ELEVENLABS_VOICE_ID}"
    payload = {
        "text":       cleaned_text,
        "model_id":   ELEVENLABS_MODEL,
        "voice_settings": {
            "stability":        min(1.0, max(0.0, (ELEVENLABS_STABILITY + params["stability"]) / 2.0)),
            "similarity_boost": min(1.0, max(0.0, (ELEVENLABS_SIMILARITY + params["similarity_boost"]) / 2.0)),
            "style":            params.get("style", 0.20),
            "speed":            params.get("speed", 1.04),
            "use_speaker_boost": True,
        },
    }

    try:
        client = _get_client()
        resp = await client.post(url, json=payload)

        if resp.status_code == 401:
            logger.error("ElevenLabs: Invalid API key")
            return None
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("retry-after", 5))
            logger.warning("ElevenLabs: Rate limited — waiting %ds then retrying", retry_after)
            await asyncio.sleep(retry_after)
            # Retry once
            resp2 = await client.post(url, json=payload)
            if resp2.status_code != 200:
                logger.warning("ElevenLabs: Still rate limited — falling back to browser TTS")
                return None
            resp2.raise_for_status()
            out.write_bytes(resp2.content)
            return out

        resp.raise_for_status()
        out.write_bytes(resp.content)
        logger.debug("ElevenLabs TTS: %s (%d bytes)", out.name, len(resp.content))
        return out

    except Exception as e:
        logger.warning("ElevenLabs synthesis failed: %s", e)
        return None


async def synthesise(text: str, emotion: str = "neutral") -> Optional[Path]:
    """Unified synthesise — picks backend from settings."""
    if TTS_BACKEND == "elevenlabs":
        return await synthesise_elevenlabs(text, emotion)
    if TTS_BACKEND == "piper":
        from core.voice.tts import synthesise_piper
        return await synthesise_piper(text, emotion)
    return None


def tts_backend() -> str:
    if TTS_BACKEND == "elevenlabs" and ELEVENLABS_API_KEY:
        return "elevenlabs"
    if TTS_BACKEND == "piper":
        return "piper"
    return "browser"
