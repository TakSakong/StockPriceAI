import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.scan import ScanJob, ScanResult
from app.models.user import User
from app.schemas.scanner import ScanJobCreate, ScanJobOut, ScanResultOut
from app.services.auth import get_current_user

router = APIRouter(prefix="/scanner", tags=["Scanner"])


@router.post("/jobs", response_model=ScanJobOut, status_code=201, summary="스캔 작업 시작")
async def create_scan_job(
    payload: ScanJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanJobOut:
    """새로운 섹터 스캔 작업을 생성하고 ML 서비스에 요청을 보냅니다.

    데이터베이스에 스캔 작업(pending 상태)을 기록한 후, ML 서비스의 API를 호출하여 비동기 스캔을 시작합니다.

    Args:
        payload (ScanJobCreate): 스캔할 섹터 정보.
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        ScanJobOut: 생성된 스캔 작업 정보.

    Raises:
        HTTPException: ML 서비스 연결에 실패한 경우 503 Service Unavailable 발생.
    """
    job = ScanJob(
        user_id=current_user.id,
        sector=payload.sector,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # ML 서비스에 비동기 스캔 요청
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            await client.post(
                f"{settings.ML_SERVICE_URL}/api/v1/scanner/start",
                json={"job_id": str(job.id), "sector": payload.sector},
            )
        except httpx.RequestError:
            job.status = "failed"
            db.commit()
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ML service unavailable",
            )

    return ScanJobOut.model_validate(job)


@router.get("/jobs/{job_id}", response_model=ScanJobOut, summary="스캔 작업 상태 조회")
def get_scan_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanJobOut:
    """특정 스캔 작업의 현재 상태(pending, processing, completed, failed)를 조회합니다.

    Args:
        job_id (uuid.UUID): 조회할 작업의 고유 ID.
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        ScanJobOut: 스캔 작업 상태 정보.

    Raises:
        HTTPException: 작업을 찾을 수 없거나 권한이 없는 경우 404 Not Found 발생.
    """
    job = db.query(ScanJob).filter(ScanJob.id == job_id, ScanJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")
    return ScanJobOut.model_validate(job)


@router.get("/jobs/{job_id}/results", response_model=list[ScanResultOut], summary="스캔 결과 조회")
def get_scan_results(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScanResultOut]:
    """완료된 스캔 작업의 상세 결과 리스트를 조회합니다.

    Args:
        job_id (uuid.UUID): 조회할 작업의 고유 ID.
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[ScanResultOut]: 스캔 결과 종목 리스트.

    Raises:
        HTTPException: 작업을 찾을 수 없는 경우 404 Not Found 발생.
    """
    job = db.query(ScanJob).filter(ScanJob.id == job_id, ScanJob.user_id == current_user.id).first()
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")

    results = db.query(ScanResult).filter(ScanResult.job_id == job_id).all()
    return [ScanResultOut.model_validate(r) for r in results]


@router.get("/jobs", response_model=list[ScanJobOut], summary="내 스캔 작업 목록")
def list_scan_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScanJobOut]:
    """현재 사용자가 요청한 최근 스캔 작업 목록(최대 20개)을 조회합니다.

    Args:
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[ScanJobOut]: 스캔 작업 이력 리스트.
    """
    jobs = (
        db.query(ScanJob)
        .filter(ScanJob.user_id == current_user.id)
        .order_by(ScanJob.created_at.desc())
        .limit(20)
        .all()
    )
    return [ScanJobOut.model_validate(j) for j in jobs]
