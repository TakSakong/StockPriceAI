"""scan_tasks.py 단위 테스트 — Redis mock으로 외부 의존성 격리"""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


# ── _save_progress ────────────────────────────────────────────

@patch("app.workers.scan_tasks._get_redis")
def test_save_progress_stores_json_in_redis(mock_get_redis) -> None:
    """_save_progress가 올바른 키/TTL/JSON으로 setex를 호출한다."""
    from app.workers.scan_tasks import PROGRESS_KEY_PREFIX, PROGRESS_TTL, _save_progress

    mock_r = MagicMock()
    mock_get_redis.return_value = mock_r

    _save_progress("job-1", {"status": "running", "done": 3})

    mock_r.setex.assert_called_once()
    key, ttl, raw = mock_r.setex.call_args[0]
    assert key == f"{PROGRESS_KEY_PREFIX}job-1"
    assert ttl == PROGRESS_TTL
    assert json.loads(raw)["status"] == "running"


@patch("app.workers.scan_tasks._get_redis")
def test_save_progress_silently_ignores_redis_error(mock_get_redis) -> None:
    """Redis 오류 발생 시 예외를 외부로 전파하지 않는다."""
    from app.workers.scan_tasks import _save_progress

    mock_get_redis.side_effect = Exception("Redis down")
    _save_progress("job-1", {"status": "running"})  # 예외 없이 통과


# ── get_scan_progress ─────────────────────────────────────────

@patch("app.workers.scan_tasks._get_redis")
def test_get_scan_progress_returns_parsed_dict(mock_get_redis) -> None:
    """Redis에 데이터가 있으면 파싱된 dict를 반환한다."""
    from app.workers.scan_tasks import get_scan_progress

    mock_r = MagicMock()
    mock_r.get.return_value = json.dumps({"status": "running", "done": 5, "total": 10})
    mock_get_redis.return_value = mock_r

    result = get_scan_progress("job-1")

    assert result is not None
    assert result["status"] == "running"
    assert result["done"] == 5


@patch("app.workers.scan_tasks._get_redis")
def test_get_scan_progress_returns_none_when_key_missing(mock_get_redis) -> None:
    """Redis에 키가 없으면 None을 반환한다."""
    from app.workers.scan_tasks import get_scan_progress

    mock_r = MagicMock()
    mock_r.get.return_value = None
    mock_get_redis.return_value = mock_r

    result = get_scan_progress("nonexistent")

    assert result is None


@patch("app.workers.scan_tasks._get_redis")
def test_get_scan_progress_returns_none_on_redis_error(mock_get_redis) -> None:
    """Redis 오류 시 None을 반환하고 예외를 전파하지 않는다."""
    from app.workers.scan_tasks import get_scan_progress

    mock_get_redis.side_effect = Exception("connection error")

    result = get_scan_progress("job-1")

    assert result is None


# ── run_scan_job (Celery 태스크) ──────────────────────────────

@patch("app.workers.scan_tasks._save_progress")
@patch("app.pipelines.scanner.run_sp500_scan")
def test_run_scan_job_completes_and_saves_final_state(mock_scan, mock_save) -> None:
    """스캔 성공 시 status=completed 최종 상태를 Redis에 저장한다."""
    from app.workers.celery_app import celery_app
    from app.workers.scan_tasks import run_scan_job

    mock_scan.return_value = (pd.DataFrame(), {})

    celery_app.conf.task_always_eager = True
    try:
        result = run_scan_job.apply(
            kwargs={"job_id": "job-ok", "tickers": ["AAPL", "MSFT"], "max_workers": 1}
        ).get()
    finally:
        celery_app.conf.task_always_eager = False

    assert result["status"] == "completed"
    assert result["job_id"] == "job-ok"
    # 최종 저장 호출 확인 (초기 + 완료 최소 2회)
    assert mock_save.call_count >= 2
    last_saved = mock_save.call_args_list[-1][0][1]
    assert last_saved["status"] == "completed"


@patch("app.workers.scan_tasks._save_progress")
@patch("app.pipelines.scanner.run_sp500_scan")
def test_run_scan_job_saves_failed_state_on_exception(mock_scan, mock_save) -> None:
    """스캔 중 예외 발생 시 status=failed 상태를 Redis에 저장하고 예외를 재발생시킨다."""
    from app.workers.celery_app import celery_app
    from app.workers.scan_tasks import run_scan_job

    mock_scan.side_effect = RuntimeError("scan crashed")

    celery_app.conf.task_always_eager = True
    try:
        with pytest.raises(RuntimeError, match="scan crashed"):
            run_scan_job.apply(
                kwargs={"job_id": "job-fail", "tickers": ["AAPL"], "max_workers": 1}
            ).get()
    finally:
        celery_app.conf.task_always_eager = False

    # failed 상태가 저장되었는지 확인
    saved_states = [call[0][1] for call in mock_save.call_args_list]
    assert any(s.get("status") == "failed" for s in saved_states)
