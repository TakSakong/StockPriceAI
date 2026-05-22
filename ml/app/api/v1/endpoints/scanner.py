"""
/api/v1/scanner — 배치 스캔 엔드포인트
POST /api/v1/scanner/start  — 스캔 작업 시작 (Celery 비동기)
GET  /api/v1/scanner/status/{job_id} — 작업 상태 조회
GET  /api/v1/scanner/tickers — S&P 500 종목 목록
GET  /api/v1/scanner/cache/stats — 캐시 통계
"""

import logging
import uuid

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ....pipelines.scanner import SP500_TICKERS, get_cache_stats
from ....workers.scan_tasks import _save_progress, get_scan_progress, run_scan_job

router = APIRouter()
log = logging.getLogger("stockai.api.scanner")


class ScanStartRequest(BaseModel):
    tickers: list[str] | None = Field(
        default=None, description="스캔할 종목 목록. None이면 S&P 500 전체"
    )
    max_workers: int = Field(default=2, ge=1, le=4, description="병렬 워커 수")
    force_refresh: bool = Field(default=False, description="캐시 무시 강제 재분석")
    period_days: int = Field(default=400, ge=100, le=1000, description="분석 기간(일)")


class ScanStartResponse(BaseModel):
    job_id: str
    status: str
    total: int
    message: str


class ScanStatusResponse(BaseModel):
    job_id: str
    status: str
    total: int
    done: int
    pct: float
    cached: int
    refreshed: int
    failed: int
    current_ticker: str
    elapsed_sec: float | None = None
    eta_sec: float | None = None
    results: list[dict] = []
    error: str | None = None


@router.post("/start", response_model=ScanStartResponse, summary="배치 스캔 시작")
async def start_scan(req: ScanStartRequest):
    """
    S&P 500 (또는 지정된 종목) 배치 스캔을 Celery 비동기 작업으로 시작합니다.

    - 반환된 **job_id**로 `/scanner/status/{job_id}` 에서 진행률 조회
    - WebSocket `/ws/scanner/{job_id}` 로 실시간 진행률 수신 가능
    - 결과는 Redis에 24시간 캐싱
    """
    tickers = req.tickers or SP500_TICKERS
    if not tickers:
        raise HTTPException(status_code=400, detail="종목 목록이 비어 있습니다")

    # 알 수 없는 종목 필터링 없음 — yfinance가 처리
    tickers = [t.strip().upper() for t in tickers]

    job_id = str(uuid.uuid4())

    # apply_async 전에 초기 상태 저장 — worker가 태스크를 처리하기 전 status 조회 시 404 방지
    _save_progress(
        job_id,
        {
            "job_id": job_id,
            "status": "queued",
            "total": len(tickers),
            "done": 0,
            "pct": 0.0,
            "cached": 0,
            "refreshed": 0,
            "failed": 0,
            "current_ticker": "",
        },
    )

    try:
        run_scan_job.apply_async(
            kwargs={
                "job_id": job_id,
                "tickers": tickers,
                "max_workers": req.max_workers,
                "force_refresh": req.force_refresh,
                "period_days": req.period_days,
            },
            task_id=job_id,
        )
    except Exception as e:
        log.error(f"Celery 태스크 시작 실패: {e}")
        raise HTTPException(status_code=503, detail="스캔 작업 시작 실패 (Celery/Redis 연결 확인)")

    return ScanStartResponse(
        job_id=job_id,
        status="queued",
        total=len(tickers),
        message=f"{len(tickers)}개 종목 스캔이 시작되었습니다. job_id={job_id}",
    )


@router.get("/status/{job_id}", response_model=ScanStatusResponse, summary="스캔 진행률 조회")
async def get_scan_status(job_id: str):
    """
    스캔 작업의 현재 진행 상태를 반환합니다.

    - **status**: queued / running / completed / failed
    - **results**: 완료된 종목의 상위 50개 결과
    """
    progress = get_scan_progress(job_id)
    if progress is None:
        raise HTTPException(status_code=404, detail=f"작업을 찾을 수 없습니다: {job_id}")

    return ScanStatusResponse(
        job_id=job_id,
        status=progress.get("status", "unknown"),
        total=progress.get("total", 0),
        done=progress.get("done", 0),
        pct=progress.get("pct", 0.0),
        cached=progress.get("cached", 0),
        refreshed=progress.get("refreshed", 0),
        failed=progress.get("failed", 0),
        current_ticker=progress.get("current_ticker", ""),
        elapsed_sec=progress.get("elapsed_sec"),
        eta_sec=progress.get("eta_sec"),
        results=progress.get("results", []),
        error=progress.get("error"),
    )


@router.get("/tickers", response_model=list[str], summary="S&P 500 종목 목록")
async def list_tickers():
    """스캐너에서 사용하는 S&P 500 종목 코드 목록을 반환합니다."""
    return SP500_TICKERS


@router.get("/cache/stats", summary="캐시 통계")
async def cache_stats(
    limit: int = Query(default=50, ge=1, le=500, description="확인할 종목 수"),
):
    """Redis에 캐싱된 스캔 결과 통계를 반환합니다."""
    tickers = SP500_TICKERS[:limit]
    try:
        stats = get_cache_stats(tickers)
        return stats
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
