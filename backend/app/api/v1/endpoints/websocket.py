
import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services import scanner as scanner_service

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/scanner/{scan_id}")
async def scanner_ws(scan_id: str, ws: WebSocket) -> None:
    """실시간 스캔 진행 상황을 ML 서비스의 /status 엔드포인트를 주기적으로 폴링하여 클라이언트에 스트리밍합니다.

    Args:
        scan_id (str): 구독할 스캔 작업의 고유 ID.
        ws (WebSocket): 웹소켓 연결 객체.
    """
    await ws.accept()
    client = scanner_service.get_http_client()
    try:
        while True:
            try:
                response = await client.get(
                    f"{settings.ML_SERVICE_URL}/api/v1/scanner/status/{scan_id}"
                )
                if response.status_code == 200:
                    data = response.json()
                    ml_status = data.get("status")
                    
                    # 프론트엔드 ScanProgressMessage 규격에 맞게 변환
                    msg_type = "progress"
                    if ml_status == "completed":
                        msg_type = "complete"
                    elif ml_status == "failed":
                        msg_type = "error"
                        
                    payload = {
                        "type": msg_type,
                        "job_id": data.get("job_id"),
                        "processed": data.get("done", 0),
                        "total": data.get("total", 0),
                        "ticker": data.get("current_ticker", ""),
                        "message": ml_status
                    }
                    
                    await ws.send_json(payload)
                    
                    if ml_status in ("completed", "failed"):
                        break
                else:
                    await ws.send_json({"type": "error", "message": f"ML service status error {response.status_code}"})
                    break
            except Exception as e:
                await ws.send_json({"type": "error", "message": str(e)})
                break
            
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        pass
