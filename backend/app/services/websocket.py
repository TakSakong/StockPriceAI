from collections import defaultdict
from typing import Any

from fastapi import WebSocket


class ConnectionManager:
    """WebSocket 연결을 scan_id별로 관리하는 매니저."""

    def __init__(self) -> None:
        self._connections: dict[str, list[WebSocket]] = defaultdict(list)

    async def connect(self, scan_id: str, ws: WebSocket) -> None:
        await ws.accept()
        self._connections[scan_id].append(ws)

    def disconnect(self, scan_id: str, ws: WebSocket) -> None:
        connections = self._connections.get(scan_id, [])
        if ws in connections:
            connections.remove(ws)

    async def broadcast(self, scan_id: str, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for ws in self._connections.get(scan_id, []):
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(scan_id, ws)


manager = ConnectionManager()
