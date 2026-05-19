from datetime import datetime, timedelta
import pytest
import uuid
import httpx
from unittest.mock import AsyncMock, patch
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models.scan import ScanJob, ScanResult
from app.services.scanner import create_scan_job, get_scan_job, get_scan_results, list_scan_jobs


@pytest.mark.asyncio
@patch("app.services.scanner.redis_client")
async def test_create_scan_job_success(mock_redis, setup_db, db_session: Session):
    """스캔 작업 생성이 성공적으로 DB에 'queued' 상태로 등록되고 Redis 메시지 큐에 정상 Push되는지 확인합니다."""
    user_id = uuid.uuid4()
    sector = "Technology"
    mock_redis.rpush = AsyncMock()

    job = await create_scan_job(user_id=user_id, sector=sector, db=db_session)

    # 검증: 대기(queued) 상태로 생성되고 반환되었는지 확인
    assert job.sector == sector
    assert job.status == "queued"
    
    # Redis 메시지 큐에 정상 rpush 호출되었는지 확인
    mock_redis.rpush.assert_called_once()
    call_args = mock_redis.rpush.call_args[0]
    assert call_args[0] == "backend:queue:scan_jobs"
    
    # 큐 등록 페이로드 정보 검증
    payload = json.loads(call_args[1])
    assert payload["job_id"] == str(job.id)
    assert payload["sector"] == sector


import json

@pytest.mark.asyncio
@patch("app.services.scanner.redis_client")
async def test_create_scan_job_ml_offline(mock_redis, setup_db, db_session: Session):
    """Redis 메시지 큐가 오프라인일 경우, 503 에러가 정상 반환되고 DB 작업 상태가 failed로 변경되는지 확인합니다."""
    user_id = uuid.uuid4()
    sector = "Technology"
    mock_redis.rpush = AsyncMock(side_effect=Exception("Redis offline"))

    with pytest.raises(HTTPException) as exc_info:
        await create_scan_job(user_id=user_id, sector=sector, db=db_session)

    assert exc_info.value.status_code == 503
    assert "Message queue unavailable" in exc_info.value.detail

    # DB 검증: 상태가 failed로 자동 처리되었는지 확인
    db_job = db_session.query(ScanJob).filter(ScanJob.user_id == user_id).first()
    assert db_job is not None
    assert db_job.status == "failed"



@pytest.mark.asyncio
async def test_get_scan_job_ownership_success(setup_db, db_session: Session):
    """자신이 생성한 스캔 작업을 성공적으로 조회하는지 검증합니다."""
    user_id = uuid.uuid4()
    
    job = ScanJob(user_id=user_id, sector="Energy", status="pending")
    db_session.add(job)
    db_session.commit()

    with patch("app.services.scanner.sync_job_status_from_ml") as mock_sync:
        mock_sync.return_value = job
        result = await get_scan_job(job_id=job.id, user_id=user_id, db=db_session)
        assert result.id == job.id
        assert result.sector == "Energy"


@pytest.mark.asyncio
async def test_get_scan_job_ownership_forbidden(setup_db, db_session: Session):
    """타인의 스캔 작업을 조회하려 할 때 404 에러를 뱉는지(보안 검증) 확인합니다."""
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()
    
    job = ScanJob(user_id=owner_id, sector="Energy", status="pending")
    db_session.add(job)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        with patch("app.services.scanner.sync_job_status_from_ml") as mock_sync:
            mock_sync.return_value = job
            await get_scan_job(job_id=job.id, user_id=attacker_id, db=db_session)

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_scan_results_ownership_success(setup_db, db_session: Session):
    """자신이 생성한 스캔 작업의 매수/매도 분석 결과를 조회하는지 검증합니다."""
    user_id = uuid.uuid4()
    
    job = ScanJob(user_id=user_id, sector="Healthcare", status="completed")
    db_session.add(job)
    db_session.commit()

    res = ScanResult(
        job_id=job.id,
        ticker="PFE",
        composite_score=0.85,
        up_prob=0.88,
        signal="BUY",
        sector="Healthcare"
    )
    db_session.add(res)
    db_session.commit()

    results = await get_scan_results(job_id=job.id, user_id=user_id, db=db_session)
    assert len(results) == 1
    assert results[0].ticker == "PFE"
    assert results[0].signal == "BUY"


@pytest.mark.asyncio
async def test_get_scan_results_ownership_forbidden(setup_db, db_session: Session):
    """타인의 스캔 결과를 탈취하여 조회하려 할 때 404 에러로 격리 방어하는지 검증합니다."""
    owner_id = uuid.uuid4()
    attacker_id = uuid.uuid4()
    
    job = ScanJob(user_id=owner_id, sector="Healthcare", status="completed")
    db_session.add(job)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        await get_scan_results(job_id=job.id, user_id=attacker_id, db=db_session)

    assert exc_info.value.status_code == 404


def test_list_scan_jobs(setup_db, db_session: Session):
    """사용자가 생성했던 최근 스캔 목록들을 최신순으로 가져오는지 검증합니다."""
    user_id = uuid.uuid4()
    
    # SQLite 등에서 func.now() 동시 생성으로 인한 정렬 불확정성 방지
    now = datetime.utcnow()
    job1 = ScanJob(user_id=user_id, sector="Tech", status="completed", created_at=now - timedelta(minutes=10))
    job2 = ScanJob(user_id=user_id, sector="Bio", status="pending", created_at=now)
    db_session.add_all([job1, job2])
    db_session.commit()

    jobs = list_scan_jobs(user_id=user_id, db=db_session)
    assert len(jobs) == 2
    # 최신순 정렬 확인
    assert jobs[0].sector == "Bio"
    assert jobs[1].sector == "Tech"
