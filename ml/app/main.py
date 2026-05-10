import asyncio
import json
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from .api.v1.router import api_router
from .core.config import settings
from .workers.scan_tasks import get_scan_progress

log = logging.getLogger("stockai.ml")

app = FastAPI(
    title="StockPriceAI ML Service",
    description="ML 예측 · 기술적 분석 · 감성 분석 · S&P 500 배치 스캐너",
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "service": "ml"}


# ─────────────────────────────────────────────────────────────
# WebSocket — 스캔 진행률 실시간 전송
# ─────────────────────────────────────────────────────────────

@app.websocket("/ws/scanner/{job_id}")
async def ws_scanner_progress(websocket: WebSocket, job_id: str):
    """
    스캔 진행률을 WebSocket으로 실시간 전송합니다.

    클라이언트가 연결되면 1초마다 Redis에서 진행률을 읽어 전송합니다.
    스캔이 완료(status=completed/failed)되면 마지막 메시지 후 연결을 종료합니다.
    """
    await websocket.accept()
    log.info(f"WebSocket 연결: job_id={job_id}")

    try:
        while True:
            progress = get_scan_progress(job_id)

            if progress is None:
                await websocket.send_json(
                    {"job_id": job_id, "status": "not_found", "error": "작업을 찾을 수 없습니다"}
                )
                break

            # 결과가 너무 크면 요약만 전송 (WebSocket 페이로드 제한)
            payload = {k: v for k, v in progress.items() if k != "results"}
            payload["result_count"] = len(progress.get("results", []))
            payload["top_results"] = progress.get("results", [])[:10]

            await websocket.send_json(payload)

            if progress.get("status") in ("completed", "failed"):
                break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        log.info(f"WebSocket 연결 끊김: job_id={job_id}")
    except Exception as e:
        log.error(f"WebSocket 오류: job_id={job_id}, error={e}")
        try:
            await websocket.send_json({"status": "error", "error": str(e)})
        except Exception:
            pass
    finally:
        log.info(f"WebSocket 종료: job_id={job_id}")
