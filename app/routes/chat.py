"""
Chat WebSocket route: PC commands go to the action agent, everything else to
the conversation engine.
"""
import asyncio
import json
import logging
import traceback
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket_manager import manager
from core.conversation.engine import ConversationEngine
from core.actions.agent import ActionAgent
from core.voice.elevenlabs_tts import synthesise, tts_backend

logger = logging.getLogger(__name__)
router  = APIRouter()


def _greeting() -> str:
    from core.personalization.persona import load
    from core.personalization.profile import load_profile
    name = load()["name"]
    user = load_profile().get("display_name")
    return f"Hey{' ' + user if user else ''}! {name} here. What's up?"
_engines: dict = {}


# Browsers don't apply CORS to WebSockets, so any website you visit could
# otherwise connect to ws://127.0.0.1:8000 and drive your PC through Yashi.
ALLOWED_ORIGINS = {
    "http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:4173", "http://127.0.0.1:4173",
    "http://localhost:8000", "http://127.0.0.1:8000",                 # desktop app
}


@router.websocket("/ws/chat/{client_id}")
async def chat_ws(websocket: WebSocket, client_id: str):
    origin = websocket.headers.get("origin")
    if origin not in ALLOWED_ORIGINS:
        logger.warning("Refused chat socket from origin %r", origin)
        await websocket.close(code=1008)
        return
    await manager.connect(client_id, websocket)
    engine = ConversationEngine()
    agent = ActionAgent()
    _engines[client_id] = engine
    active_task = None

    await manager.send(client_id, {
        "type":    "connected",
        "session": engine.session_id,
        "message": _greeting(),
    })

    async def run_pipeline(user_text: str):
        try:
            async for event in engine.process_message(user_text):
                await manager.send(client_id, event)
        except Exception as e:
            tb = traceback.format_exc()
            logger.error("process_message failed:\n%s", tb)
            await manager.send(client_id, {
                "type":      "done",
                "full_text": f"Sorry, something went wrong: {type(e).__name__}: {str(e)[:120]}",
                "audio_path": None,
                "emotion":   "neutral",
                "mode":      "standard",
                "elapsed":   0,
                "tts_backend": "browser",
            })

    try:
        while True:
            if active_task is not None and active_task.done():
                try:
                    await active_task
                except Exception:
                    pass
                active_task = None

            raw      = await websocket.receive_text()
            data     = json.loads(raw)
            msg_type = data.get("type", "text")

            if msg_type == "text":
                user_text = data.get("text", "").strip()
                if not user_text:
                    continue

                if active_task is not None and not active_task.done():
                    await manager.send(client_id, {
                        "type": "safety",
                        "note": "Yashi is still responding. Press Stop to interrupt, then send another message.",
                    })
                    continue

                # ── PC commands ───────────────────────────────────────────────
                try:
                    reply = await agent.handle(user_text)
                except Exception:
                    logger.exception("Action agent failed")
                    reply = None
                if reply:
                    # Her real voice for action replies too, not the browser's robot voice.
                    audio = None
                    if tts_backend() == "elevenlabs":
                        try:
                            path = await synthesise(reply, "happy")
                            audio = path.name if path else None
                        except Exception:
                            logger.warning("TTS for action reply failed", exc_info=True)
                    await manager.send(client_id, {"type": "plugin_response", "message": reply,
                                                   "audio_path": audio})
                    continue

                # ── Conversation pipeline ─────────────────────────────────────
                active_task = asyncio.create_task(run_pipeline(user_text))

            elif msg_type == "new_session":
                if active_task is not None and not active_task.done():
                    engine.request_stop()
                sid = engine.new_session()
                await manager.send(client_id, {"type": "session_reset", "session": sid})

            elif msg_type == "stop":
                if active_task is not None and not active_task.done():
                    engine.request_stop()

            elif msg_type == "ping":
                await manager.send(client_id, {"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Client %s disconnected", client_id)
    except Exception as e:
        logger.error("WS fatal [%s]: %s", client_id, e, exc_info=True)
    finally:
        if active_task is not None and not active_task.done():
            engine.request_stop()
            try:
                await asyncio.wait_for(active_task, timeout=2.0)
            except Exception:
                active_task.cancel()

        manager.disconnect(client_id)
        _engines.pop(client_id, None)