"""
Celery 비동기 스캔 태스크
S&P 500 배치 스캔을 백그라운드에서 실행하고
Redis에 진행률 및 결과를 저장합니다.
"""

import json
import logging
from datetime import datetime

import redis

from ..core.config import settings
from .celery_app import celery_app

log = logging.getLogger("stockai.tasks")

PROGRESS_KEY_PREFIX = "scan:progress:"
PROGRESS_TTL = 86400  # 24h


def _get_redis() -> redis.Redis:
    return redis.from_url(settings.redis_url, decode_responses=True)


def _save_progress(job_id: str, data: dict) -> None:
    try:
        r = _get_redis()
        r.setex(f"{PROGRESS_KEY_PREFIX}{job_id}", PROGRESS_TTL, json.dumps(data, default=str))
    except Exception:
        pass


def get_scan_progress(job_id: str) -> dict | None:
    try:
        r = _get_redis()
        raw = r.get(f"{PROGRESS_KEY_PREFIX}{job_id}")
        if raw:
            return json.loads(raw)
    except Exception:
        pass
    return None


@celery_app.task(bind=True, name="scan_tasks.run_scan_job", max_retries=0)
def run_scan_job(
    self,
    job_id: str,
    tickers: list[str],
    max_workers: int = 2,
    force_refresh: bool = False,
    period_days: int = 400,
) -> dict:
    """
    S&P 500 배치 스캔 Celery 태스크.

    진행률을 Redis에 저장하고, 완료 시 결과도 Redis에 저장합니다.
    WebSocket 엔드포인트는 이 Redis 키를 폴링하여 클라이언트에 전달합니다.
    """
    log.info(f"스캔 시작: job_id={job_id}, 종목={len(tickers)}")

    # 초기 상태 저장
    _save_progress(
        job_id,
        {
            "job_id": job_id,
            "status": "running",
            "total": len(tickers),
            "done": 0,
            "pct": 0.0,
            "cached": 0,
            "refreshed": 0,
            "failed": 0,
            "current_ticker": "",
            "started_at": datetime.now().isoformat(),
            "results": [],
        },
    )

    try:
        from ..services.scanner import ScanProgress, run_sp500_scan

        progress = ScanProgress(total=len(tickers))

        def on_progress(state: dict) -> None:
            _save_progress(
                job_id,
                {
                    "job_id": job_id,
                    "status": "running",
                    **state,
                    "results": [
                        {
                            k: v
                            for k, v in r.items()
                            if k
                            in (
                                "ticker",
                                "name",
                                "sector",
                                "composite_score",
                                "up_probability",
                                "estimated_upside",
                                "ml_signal",
                                "current_price",
                                "rsi",
                            )
                        }
                        for r in progress.live_results[-20:]  # 최근 20개만
                    ],
                },
            )

        scan_df, _ = run_sp500_scan(
            tickers=tickers,
            max_workers=max_workers,
            force_refresh=force_refresh,
            period_days=period_days,
            progress=progress,
            progress_callback=on_progress,
        )

        # 최종 결과 요약
        top_results = []
        if not scan_df.empty:
            top_results = (
                scan_df.head(50)[
                    [
                        "ticker",
                        "name",
                        "sector",
                        "composite_score",
                        "up_probability",
                        "estimated_upside",
                        "ml_signal",
                        "current_price",
                        "rsi",
                        "buy_signals",
                        "market_cap",
                    ]
                ]
                .fillna(0)
                .to_dict("records")
            )

        final_state = {
            "job_id": job_id,
            "status": "completed",
            "total": len(tickers),
            "done": progress.done,
            "pct": 100.0,
            "cached": progress.cached,
            "refreshed": progress.refreshed,
            "failed": progress.failed,
            "current_ticker": "",
            "elapsed_sec": round(progress.elapsed_sec, 1),
            "eta_sec": None,
            "results": top_results,
            "completed_at": datetime.now().isoformat(),
        }
        _save_progress(job_id, final_state)
        log.info(f"스캔 완료: job_id={job_id}, 성공={progress.refreshed + progress.cached}")
        return final_state

    except Exception as e:
        error_state = {
            "job_id": job_id,
            "status": "failed",
            "error": str(e),
            "failed_at": datetime.now().isoformat(),
        }
        _save_progress(job_id, error_state)
        log.error(f"스캔 실패: job_id={job_id}, error={e}")
        raise
