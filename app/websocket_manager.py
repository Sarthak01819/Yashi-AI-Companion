"""
WebSocket connection manager — handles multiple concurrent clients.
"""

import logging
import json
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        self.active: Dict[str, WebSocket] = {}

    async def connect(self, client_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self.active[client_id] = ws
        logger.info("WS connected: %s  (total: %d)", client_id, len(self.active))

    def disconnect(self, client_id: str) -> None:
        self.active.pop(client_id, None)
        logger.info("WS disconnected: %s  (total: %d)", client_id, len(self.active))

    async def send(self, client_id: str, data: dict) -> None:
        ws = self.active.get(client_id)
        if ws:
            try:
                await ws.send_text(json.dumps(data))
            except Exception as e:
                logger.warning("WS send error [%s]: %s", client_id, e)
                self.disconnect(client_id)

    async def broadcast(self, data: dict) -> None:
        disconnected = []
        for cid, ws in list(self.active.items()):
            try:
                await ws.send_text(json.dumps(data))
            except Exception:
                disconnected.append(cid)
        for cid in disconnected:
            self.disconnect(cid)


manager = ConnectionManager()
