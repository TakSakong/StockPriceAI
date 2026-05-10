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
    jobs = (
        db.query(ScanJob)
        .filter(ScanJob.user_id == current_user.id)
        .order_by(ScanJob.created_at.desc())
        .limit(20)
        .all()
    )
    return [ScanJobOut.model_validate(j) for j in jobs]
