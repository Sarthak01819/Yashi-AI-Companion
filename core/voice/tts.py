"""
Text-to-speech — two backends:
  1. piper-tts (pip package) — high quality, offline
  2. Browser Web Speech API signal — tells frontend to use built-in TTS (zero install)

Streaming: splits response into sentences and synthesises each one immediately.
"""

import re
import hashlib
import logging
import asyncio
from pathlib import Path
from typing import Optional, AsyncGenerator

from config.settings import (
    PIPER_MODEL_DIR,
    PIPER_DEFAULT_VOICE,
    PIPER_OUTPUT_DIR,
)

logger = logging.getLogger(__name__)

# Emotion → speaking rate (for both Piper and browser TTS)
EMOTION_SPEED_MAP = {
    "distressed": 0.82,
    "sad":        0.88,
    "concerned":  0.90,
    "neutral":    1.00,
    "content":    1.00,
    "happy":      1.06,
    "joyful":     1.12,
    "excited":    1.15,
}

# Try to import piper at module level
_piper_available = False
try:
    from piper.voice import PiperVoice
    _piper_available = True
    logger.info("piper-tts package found — will use Piper for TTS")
except ImportError:
    logger.info("piper-tts not installed — TTS will use browser Web Speech API")

_piper_voice_cache = {}


def _get_piper_voice(voice_name: str):
    """Load and cache a Piper voice model."""
    if voice_name in _piper_voice_cache:
        return _piper_voice_cache[voice_name]
    model_path = Path(PIPER_MODEL_DIR) / f"{voice_name}.onnx"
    if not model_path.exists():
        logger.warning("Piper model not found: %s", model_path)
        return None
    from piper.voice import PiperVoice
    voice = PiperVoice.load(str(model_path))
    _piper_voice_cache[voice_name] = voice
    logger.info("Piper voice loaded: %s", voice_name)
    return voice


def _cache_path(text: str) -> Path:
    h = hashlib.sha1(text.encode()).hexdigest()[:16]
    return Path(PIPER_OUTPUT_DIR) / f"{h}.wav"


async def synthesise_piper(text: str, emotion: str = "neutral") -> Optional[Path]:
    """Synthesise with piper-tts pip package. Returns WAV path or None."""
    if not _piper_available or not text.strip():
        return None

    Path(PIPER_OUTPUT_DIR).mkdir(parents=True, exist_ok=True)
    out_path = _cache_path(text)
    if out_path.exists():
        return out_path

    try:
        voice = _get_piper_voice(PIPER_DEFAULT_VOICE)
        if voice is None:
            return None

        import wave

        def _synth():
            with wave.open(str(out_path), "w") as wf:
                voice.synthesize(text, wf)

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, _synth)
        logger.debug("TTS → %s", out_path.name)
        return out_path
    except Exception as e:
        logger.warning("Piper synthesis failed: %s", e)
        return None


def split_sentences(text: str) -> list[str]:
    """Split text into speakable sentence chunks."""
    text = text.strip()
    if not text:
        return []
    # Split on sentence-ending punctuation
    parts = re.split(r'(?<=[.!?])\s+', text)
    # Merge very short fragments
    merged, buf = [], ""
    for p in parts:
        buf = (buf + " " + p).strip() if buf else p
        if len(buf) >= 40:
            merged.append(buf)
            buf = ""
    if buf:
        merged.append(buf)
    return merged


async def synthesise(text: str, emotion: str = "neutral") -> Optional[Path]:
    """Synthesise full text. Returns WAV path if Piper available, else None."""
    if _piper_available:
        return await synthesise_piper(text, emotion)
    return None


def is_piper_available() -> bool:
    return _piper_available


def tts_backend() -> str:
    """Returns which TTS backend is active."""
    if not _piper_available:
        return "browser"
    model_path = Path(PIPER_MODEL_DIR) / f"{PIPER_DEFAULT_VOICE}.onnx"
    if model_path.exists():
        return "piper"
    return "browser"
