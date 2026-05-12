"""
Chat WebSocket route — handles text messages and plugin dispatch.
"""
import asyncio
import json
import logging
import traceback
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.websocket_manager import manager
from core.conversation.engine import ConversationEngine
from plugins.plugin_loader import dispatch as plugin_dispatch

logger = logging.getLogger(__name__)
router  = APIRouter()
_engines: dict = {}


@router.websocket("/ws/chat/{client_id}")
async def chat_ws(websocket: WebSocket, client_id: str):
    await manager.connect(client_id, websocket)
    engine = ConversationEngine()
    _engines[client_id] = engine
    active_task = None

    await manager.send(client_id, {
        "type":    "connected",
        "session": engine.session_id,
        "message": "Yashi is ready. How can I be here for you today?",
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

                # ── Plugin dispatch ───────────────────────────────────────────
                try:
                    pr = await plugin_dispatch(user_text, {"session_id": engine.session_id})
                    if pr.get("success") and pr.get("message"):
                        await manager.send(client_id, {
                            "type":    "plugin_response",
                            "plugin":  pr.get("data", {}),
                            "message": pr["message"],
                        })
                        continue
                except Exception as pe:
                    logger.warning("Plugin error: %s", pe)

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