"""Bütün qoşulmuş dashboard-lara canlı JSON hadisələri yayan WebSocket meneceri."""
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        self.active: dict[WebSocket, int] = {}

    async def connect(self, websocket: WebSocket, workspace_id: int) -> None:
        await websocket.accept()
        self.active[websocket] = workspace_id

    def disconnect(self, websocket: WebSocket) -> None:
        self.active.pop(websocket, None)

    async def broadcast(self, message: dict) -> None:
        if not self.active:
            return
        payload = json.dumps(message, default=str)
        dead = []
        workspace_id = message.get("workspace_id")
        if workspace_id is None:
            logger.warning("Workspace-siz WebSocket hadisəsi bloklandı: %s", message.get("type"))
            return
        for websocket, connection_workspace_id in list(self.active.items()):
            if workspace_id is not None and connection_workspace_id != workspace_id:
                continue
            try:
                await websocket.send_text(payload)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            self.disconnect(websocket)


manager = ConnectionManager()
