import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.scanner import ScanJobCreate, ScanJobOut, ScanResultOut
from app.services.auth import get_current_user
from app.services import scanner as scanner_service

router = APIRouter(prefix="/scanner", tags=["Scanner"])


@router.post("/jobs", response_model=ScanJobOut, status_code=201, summary="스캔 작업 시작")
async def create_scan_job(
    payload: ScanJobCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanJobOut:
    """새로운 섹터 스캔 작업을 생성하고 ML 서비스에 요청을 보냅니다.

    데이터베이스에 스캔 작업(pending 상태)을 기록한 후, ML 서비스의 API를 호출하여 비동기 스캔을 시작합니다.
    """
    return await scanner_service.create_scan_job(
        user_id=current_user.id,
        sector=payload.sector,
        db=db,
    )


@router.get("/jobs/{job_id}", response_model=ScanJobOut, summary="스캔 작업 상태 조회")
async def get_scan_job(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ScanJobOut:
    """특정 스캔 작업의 현재 상태(pending, processing, completed, failed)를 조회합니다.
    """
    return await scanner_service.get_scan_job(
        job_id=job_id,
        user_id=current_user.id,
        db=db,
    )


@router.get("/jobs/{job_id}/results", response_model=list[ScanResultOut], summary="스캔 결과 조회")
async def get_scan_results(
    job_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScanResultOut]:
    """완료된 스캔 작업의 상세 결과 리스트를 조회합니다.
    """
    return await scanner_service.get_scan_results(
        job_id=job_id,
        user_id=current_user.id,
        db=db,
    )


@router.get("/jobs", response_model=list[ScanJobOut], summary="내 스캔 작업 목록")
def list_scan_jobs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ScanJobOut]:
    """현재 사용자가 요청한 최근 스캔 작업 목록(최대 20개)을 조회합니다.
    """
    return scanner_service.list_scan_jobs(
        user_id=current_user.id,
        db=db,
    )
