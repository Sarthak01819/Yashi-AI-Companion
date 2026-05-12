"""
Audio routes — receive mic audio chunks, return transcription + trigger conversation.
"""

import io
import uuid
import base64
import logging
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket_manager import manager
from core.voice.stt import transcribe
from core.voice.vad import SimpleVAD
from core.conversation.engine import ConversationEngine
from plugins.plugin_loader import dispatch as plugin_dispatch
from config.settings import SAMPLE_RATE

logger = logging.getLogger(__name__)
router = APIRouter()
_audio_engines: dict = {}


@router.websocket("/ws/audio/{client_id}")
async def audio_ws(websocket: WebSocket, client_id: str):
    """
    Receives raw PCM int16 audio chunks as base64 strings.
    Performs VAD → Whisper STT → Conversation Engine.
    """
    await manager.connect(client_id, websocket)
    vad = SimpleVAD()
    engine = ConversationEngine()
    _audio_engines[client_id] = engine

    await manager.send(client_id, {
        "type":    "audio_ready",
        "session": engine.session_id,
        "sample_rate": SAMPLE_RATE,
    })

    try:
        while True:
            raw = await websocket.receive_text()
            data = json_loads_safe(raw)
            if not data:
                continue

            chunk_b64 = data.get("audio_chunk")
            if not chunk_b64:
                continue

            # Decode PCM
            pcm_bytes = base64.b64decode(chunk_b64)
            chunk_np = np.frombuffer(pcm_bytes, dtype=np.int16)

            result = vad.process_chunk(chunk_np)

            if result["end_of_speech"]:
                audio_buf = vad.get_audio_buffer()
                vad.reset()

                await manager.send(client_id, {"type": "transcribing"})
                text = transcribe(audio_buf)

                if text.strip():
                    await manager.send(client_id, {"type": "transcribed", "text": text})

                    # Plugin check
                    plugin_result = await plugin_dispatch(text, {"session_id": engine.session_id})
                    if plugin_result.get("success") and plugin_result.get("message"):
                        await manager.send(client_id, {
                            "type":    "plugin_response",
                            "message": plugin_result["message"],
                        })
                        continue

                    # Full conversation pipeline
                    async for event in engine.process_message(text, audio_np=audio_buf):
                        await manager.send(client_id, event)

            elif result["speech_detected"]:
                await manager.send(client_id, {"type": "listening"})

    except WebSocketDisconnect:
        logger.info("Audio client %s disconnected", client_id)
    except Exception as e:
        logger.error("Audio WS error [%s]: %s", client_id, e, exc_info=True)
    finally:
        manager.disconnect(client_id)
        _audio_engines.pop(client_id, None)


def json_loads_safe(s: str) -> dict:
    import json
    try:
        return json.loads(s)
    except Exception:
        return {}
