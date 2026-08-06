import json
import logging
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class WebSocketManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, project_id: str, websocket: WebSocket):
        await websocket.accept()
        if project_id not in self._connections:
            self._connections[project_id] = []
        self._connections[project_id].append(websocket)
        logger.info(f"WebSocket connected for project {project_id}. Total connections: {len(self._connections[project_id])}")

    def disconnect(self, project_id: str, websocket: WebSocket):
        if project_id in self._connections:
            self._connections[project_id].remove(websocket)
            if not self._connections[project_id]:
                del self._connections[project_id]
        logger.info(f"WebSocket disconnected for project {project_id}")

    async def broadcast(self, project_id: str, message: dict):
        connections = self._connections.get(project_id, [])
        if not connections:
            logger.warning(f"No WebSocket connections for project {project_id}. Message dropped: {message.get('type')}")
            return

        logger.info(f"Broadcasting to {len(connections)} client(s): {message.get('type')} - {message.get('payload', {}).get('message', message.get('payload', {}).get('title', ''))[:80]}")

        dead = []
        for ws in connections:
            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.error(f"WebSocket send failed: {e}")
                dead.append(ws)
        for ws in dead:
            self.disconnect(project_id, ws)


manager = WebSocketManager()
