
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services import scanner as scanner_service
from app.core.config import settings

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/scanner/{scan_id}")
async def scanner_ws(scan_id: str, ws: WebSocket) -> None:
    """실시간 스캔 진행 상황을 백엔드 메시지 큐 대기상태 및 ML 서비스 상태를 기반으로 클라이언트에 스트리밍합니다."""
    await ws.accept()
    client = scanner_service.get_http_client()
    from app.core.redis import redis_client
    try:
        while True:
            try:
                # 1. Redis에서 매핑된 ML ID 조회
                ml_job_id = await redis_client.get(f"scan:job_map:backend:{scan_id}")
                
                # 2. 매핑이 없다면 큐에 대기 중이므로 queued 상태 메시지 응답
                if not ml_job_id:
                    payload = {
                        "type": "progress",
                        "job_id": scan_id,
                        "processed": 0,
                        "total": 0,
                        "ticker": "",
                        "message": "queued"
                    }
                    await ws.send_json(payload)
                    await asyncio.sleep(1.5)
                    continue

                # 3. 매핑된 ML ID가 있다면 ML 서비스 status 조회
                response = await client.get(
                    f"{settings.ML_SERVICE_URL}/api/v1/scanner/status/{ml_job_id}"
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
                        "job_id": scan_id,
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

