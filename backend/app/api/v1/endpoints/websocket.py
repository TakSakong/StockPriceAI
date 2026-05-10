
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket import manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/scanner/{scan_id}")
async def scanner_ws(scan_id: str, ws: WebSocket) -> None:
    """실시간 스캔 진행률을 WebSocket으로 스트리밍합니다.

    클라이언트가 받는 메시지 형식:
    ```json
    {
      "type": "progress",
      "scan_id": "<uuid>",
      "processed": 42,
      "total": 500,
      "ticker": "AAPL"
    }
    ```
    또는 완료 시:
    ```json
    {"type": "done", "scan_id": "<uuid>"}
    ```
    """
    await manager.connect(scan_id, ws)
    try:
        while True:
            # 클라이언트 ping을 수신해 연결을 유지한다 (메시지가 없으면 disconnect 감지)
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(scan_id, ws)
