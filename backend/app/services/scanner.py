import logging
import uuid

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.scan import ScanJob, ScanResult
from app.schemas.scanner import ScanJobOut, ScanResultOut

log = logging.getLogger("stockai.backend.scanner")

# 커넥션 풀 재사용을 위한 글로벌 지연(Lazy) 초기화 HTTPX 클라이언트 변수
_http_client: httpx.AsyncClient | None = None


def get_http_client() -> httpx.AsyncClient:
    """이벤트 루프 내부에서 안전하게 실행되도록 HTTPX AsyncClient를 지연 초기화하여 반환합니다.
    비동기 스캔 트리거는 빠르게 완료되므로 타임아웃을 5.0초로 설정합니다.
    """
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=5.0)
    return _http_client


async def create_scan_job(
    user_id: uuid.UUID,
    sector: str | None,
    db: Session,
) -> ScanJobOut:
    """새로운 섹터 스캔 작업을 생성하고 ML 서비스에 비동기 스캔을 요청합니다.

    Args:
        user_id (uuid.UUID): 작업을 요청한 사용자의 고유 ID.
        sector (str | None): 스캔할 섹터명.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        ScanJobOut: 생성된 스캔 작업 정보.

    Raises:
        HTTPException: ML 서비스 연결에 실패한 경우 503 Service Unavailable 발생.
    """
    job = ScanJob(
        user_id=user_id,
        sector=sector,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # ML 서비스에 비동기 스캔 요청
    client = get_http_client()
    try:
        await client.post(
            f"{settings.ML_SERVICE_URL}/api/v1/scanner/start",
            json={"job_id": str(job.id), "sector": sector},
        )
    except httpx.RequestError as e:
        log.error(f"❌ ML 서비스 비동기 스캔 트리거 실패: {str(e)}")
        job.status = "failed"
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML service unavailable",
        )

    log.info(f"🚀 스캔 작업 생성 완료 및 ML 트리거 성공: Job ID={job.id}, Sector={sector}")
    return ScanJobOut.model_validate(job)


def get_scan_job(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> ScanJobOut:
    """특정 사용자가 소유한 스캔 작업의 상태 정보를 조회합니다.

    Args:
        job_id (uuid.UUID): 조회할 작업의 고유 ID.
        user_id (uuid.UUID): 요청한 사용자의 고유 ID.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        ScanJobOut: 스캔 작업 정보.

    Raises:
        HTTPException: 작업을 찾을 수 없거나 소유권이 다른 경우 404 Not Found 발생.
    """
    job = db.query(ScanJob).filter(ScanJob.id == job_id, ScanJob.user_id == user_id).first()
    if not job:
        log.warning(f"⚠️ 권한 없음 혹은 존재하지 않는 스캔 작업 조회 요청: Job ID={job_id}, User ID={user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")
    return ScanJobOut.model_validate(job)


def get_scan_results(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> list[ScanResultOut]:
    """완료된 스캔 작업의 상세 결과 리스트를 조회합니다.

    Args:
        job_id (uuid.UUID): 조회할 작업의 고유 ID.
        user_id (uuid.UUID): 요청한 사용자의 고유 ID.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[ScanResultOut]: 스캔 결과 리스트.

    Raises:
        HTTPException: 작업을 찾을 수 없거나 소유권이 다른 경우 404 Not Found 발생.
    """
    job = db.query(ScanJob).filter(ScanJob.id == job_id, ScanJob.user_id == user_id).first()
    if not job:
        log.warning(f"⚠️ 권한 없음 혹은 존재하지 않는 스캔 결과 조회 요청: Job ID={job_id}, User ID={user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")

    results = db.query(ScanResult).filter(ScanResult.job_id == job_id).all()
    return [ScanResultOut.model_validate(r) for r in results]


def list_scan_jobs(
    user_id: uuid.UUID,
    db: Session,
) -> list[ScanJobOut]:
    """현재 사용자가 요청한 최근 스캔 작업 목록(최대 20개)을 최신순으로 조회합니다.

    Args:
        user_id (uuid.UUID): 요청한 사용자의 고유 ID.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[ScanJobOut]: 최근 스캔 작업 리스트.
    """
    jobs = (
        db.query(ScanJob)
        .filter(ScanJob.user_id == user_id)
        .order_by(ScanJob.created_at.desc())
        .limit(20)
        .all()
    )
    return [ScanJobOut.model_validate(j) for j in jobs]
