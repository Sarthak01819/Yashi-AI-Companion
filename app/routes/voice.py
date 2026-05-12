"""
Voice WebSocket endpoint.
Client streams raw PCM int16 audio chunks; server does VAD + STT + full pipeline.
"""

import io
import struct
import logging
import asyncio
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket_manager import manager
from core.voice.vad import SimpleVAD
from core.voice.stt import transcribe
from core.conversation.engine import ConversationEngine
from config.settings import SAMPLE_RATE

logger = logging.getLogger(__name__)
router = APIRouter()

_voice_engines: dict = {}


@router.websocket("/ws/voice/{client_id}")
async def voice_ws(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)

    if client_id not in _voice_engines:
        _voice_engines[client_id] = ConversationEngine()

    engine = _voice_engines[client_id]
    vad = SimpleVAD()

    await manager.send(client_id, {"type": "voice_ready", "sample_rate": SAMPLE_RATE})

    try:
        while True:
            data = await websocket.receive_bytes()

            if len(data) == 0:
                continue

            # Convert bytes → int16 numpy array
            n_samples = len(data) // 2
            chunk = np.frombuffer(data, dtype=np.int16)

            result = vad.process_chunk(chunk)

            if result["speech_detected"]:
                await manager.send(client_id, {"type": "vad_status", "speaking": True, "energy": result["energy"]})

            if result["end_of_speech"]:
                audio_buffer = vad.get_audio_buffer()
                vad.reset()

                await manager.send(client_id, {"type": "transcribing"})

                # Run Whisper in thread pool (CPU-bound)
                loop = asyncio.get_event_loop()
                text = await loop.run_in_executor(None, transcribe, audio_buffer)

                if text.strip():
                    await manager.send(client_id, {"type": "transcript", "text": text})
                    # Process through full pipeline
                    async for event in engine.process_message(text, audio_np=audio_buffer):
                        await manager.send(client_id, event)
                else:
                    await manager.send(client_id, {"type": "transcript", "text": ""})
                    vad.reset()

    except WebSocketDisconnect:
        logger.info("Voice client %s disconnected", client_id)
        manager.disconnect(client_id)
    except Exception as e:
        logger.error("Voice WS error for %s: %s", client_id, e)
        manager.disconnect(client_id)
