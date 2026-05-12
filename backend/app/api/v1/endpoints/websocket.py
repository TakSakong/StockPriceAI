
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket import manager

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/scanner/{scan_id}")
async def scanner_ws(scan_id: str, ws: WebSocket) -> None:
    """실시간 스캔 진행 상황을 WebSocket을 통해 스트리밍합니다.

    클라이언트와 연결을 맺고, ML 서비스 등에서 발생하는 스캔 진행 이벤트를 
    해당 `scan_id`를 구독 중인 클라이언트들에게 전송합니다.

    Args:
        scan_id (str): 구독할 스캔 작업의 고유 ID.
        ws (WebSocket): 웹소켓 연결 객체.

    Messages:
        - progress: 현재 처리 중인 티커 및 전체 대비 진행률 정보를 포함합니다.
        - done: 모든 스캔 작업이 완료되었음을 알립니다.
    """
    await manager.connect(scan_id, ws)
    try:
        while True:
            # 클라이언트 ping을 수신해 연결을 유지한다 (메시지가 없으면 disconnect 감지)
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(scan_id, ws)
