"""
Speech-to-text API — local Whisper, so voice works in any browser
(Brave blocks the Google service that browser speech recognition uses).

POST /api/stt   body: raw 16-bit little-endian mono PCM at 16 kHz
                returns {"text": "..."}
"""
import asyncio
import logging

import numpy as np
from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from config.settings import SAMPLE_RATE
from core.voice.stt import transcribe

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

MIN_SAMPLES = SAMPLE_RATE // 4          # < 0.25 s is a click, not speech
MAX_SAMPLES = SAMPLE_RATE * 30          # Whisper's window

# One transcription at a time: the model is shared and the CPU is the limit.
_lock = asyncio.Lock()


@router.post("/stt")
async def speech_to_text(request: Request):
    body = await request.body()
    if len(body) % 2:
        body = body[:-1]
    audio = np.frombuffer(body, dtype=np.int16)
    if audio.size < MIN_SAMPLES:
        return {"text": ""}
    audio = audio[:MAX_SAMPLES]

    async with _lock:
        try:
            text = await run_in_threadpool(transcribe, audio)
        except Exception as e:
            logger.error("STT failed: %s", e)
            return {"text": "", "error": "transcription failed"}

    logger.info("STT (%.1fs audio): %r", audio.size / SAMPLE_RATE, text)
    return {"text": text}
