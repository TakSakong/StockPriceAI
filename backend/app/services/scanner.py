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


from sqlalchemy import func

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
        HTTPException: ML 서비스 연결에 실패하거나 비정상 응답인 경우 503 에러 발생.
    """
    client = get_http_client()
    try:
        # 1. ML 서비스에 비동기 스캔 트리거 요청 (ML 측에서 임의의 UUID를 자동 생성하여 결과 반환)
        response = await client.post(
            f"{settings.ML_SERVICE_URL}/api/v1/scanner/start",
            json={"sector": sector},
        )
        if response.status_code not in (200, 201):
            raise httpx.HTTPStatusError("ML returned non-success", request=None, response=response)
        
        data = response.json()
        ml_job_id = uuid.UUID(data["job_id"])
    except Exception as e:
        log.error(f"❌ ML 서비스 비동기 스캔 트리거 실패: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ML service unavailable",
        )

    # 2. ML 서비스가 돌려준 job_id를 기본 키(PK)로 지정하여 PostgreSQL DB에 기록 보존
    job = ScanJob(
        id=ml_job_id,
        user_id=user_id,
        sector=sector,
        status="pending",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    log.info(f"🚀 스캔 작업 생성 완료 및 ML 트리거 성공: Job ID={job.id}, Sector={sector}")
    return ScanJobOut.model_validate(job)


def is_sector_match(r_sector: str, job_sector: str) -> bool:
    """ML의 yfinance 영문 섹터명과 프론트엔드의 매개변수를 유연하게 매핑 및 매칭합니다."""
    if not job_sector:
        return True
    
    r_sec = r_sector.strip().lower()
    j_sec = job_sector.strip().lower()
    
    # 1. 완전 일치 검사
    if r_sec == j_sec:
        return True
        
    # 2. 동의어 매핑 (금융, 소비재, 소재 등 예외 케이스 처리)
    mapping = {
        "financials": ["financial services", "financials", "금융"],
        "consumer discretionary": ["consumer cyclical", "consumer discretionary", "소비재"],
        "materials": ["basic materials", "materials", "소재"],
    }
    
    if j_sec in mapping:
        return r_sec in mapping[j_sec]
        
    # 3. 양방향 부분 매칭
    return j_sec in r_sec or r_sec in j_sec


async def sync_job_status_from_ml(job_id: uuid.UUID, db: Session) -> ScanJob | None:
    """ML 서비스로부터 실시간 스캔 상태를 동기화하고 완료 시 섹터 필터링 결과를 백엔드 DB에 보존합니다.

    Args:
        job_id (uuid.UUID): 동기화할 작업의 고유 ID.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        ScanJob | None: 동기화된 스캔 작업 DB 모델 객체.
    """
    job = db.query(ScanJob).filter(ScanJob.id == job_id).first()
    if not job:
        return None

    # 이미 완료 또는 실패한 작업은 중복 호출 방지를 위해 패스
    if job.status in ("completed", "failed"):
        return job

    client = get_http_client()
    try:
        response = await client.get(
            f"{settings.ML_SERVICE_URL}/api/v1/scanner/status/{job_id}"
        )
        if response.status_code == 200:
            data = response.json()
            status_ml = data.get("status")
            job.total = data.get("total")
            job.processed = data.get("done")

            if status_ml == "completed":
                results_ml = data.get("results", [])
                
                # 백엔드 전용 섹터 필터링 수행 (유연한 매칭 헬퍼 사용)
                if job.sector:
                    results_ml = [
                        r for r in results_ml
                        if is_sector_match(r.get("sector", ""), job.sector)
                    ]

                # 중복 방지를 위해 기존 결과 제거
                db.query(ScanResult).filter(ScanResult.job_id == job_id).delete()
                
                for r in results_ml:
                    up_p = r.get("up_probability")
                    if up_p is not None:
                        up_val = float(up_p) / 100.0
                    else:
                        up_val = float(r.get("up_prob", 0.0))

                    res = ScanResult(
                        job_id=job_id,
                        ticker=r["ticker"],
                        composite_score=r.get("composite_score", 0.0),
                        up_prob=up_val,
                        signal=r.get("ml_signal", r.get("signal", "HOLD")),
                        sector=r.get("sector", ""),
                        est_upside=r.get("estimated_upside", 0.0),
                    )
                    db.add(res)
                
                job.status = "completed"
                job.finished_at = func.now()
                db.commit()
                db.refresh(job)
                log.info(f"✅ 스캔 작업 동기화 성공 및 PostgreSQL 결과 저장 완료: Job ID={job_id}")
            elif status_ml == "failed":
                job.status = "failed"
                job.finished_at = func.now()
                db.commit()
                db.refresh(job)
                log.warning(f"❌ 스캔 작업 동기화 - ML 측 실패 확인: Job ID={job_id}")
            elif status_ml in ("running", "processing"):
                # 프론트엔드가 진행 상태바를 렌더링할 수 있도록 DB 상태를 "running"으로 설정
                if job.status != "running":
                    job.status = "running"
                    if not job.started_at:
                        job.started_at = func.now()
                    db.commit()
                    db.refresh(job)
    except Exception as e:
        log.warning(f"⚠️ ML 서비스로부터 스캔 상태 동기화 중 오류 발생: {str(e)}")

    return job


async def get_scan_job(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> ScanJobOut:
    """특정 사용자가 소유한 스캔 작업의 상태 정보를 조회하며, 필요시 ML 서비스와 실시간 동기화합니다.

    Args:
        job_id (uuid.UUID): 조회할 작업의 고유 ID.
        user_id (uuid.UUID): 요청한 사용자의 고유 ID.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        ScanJobOut: 스캔 작업 정보.

    Raises:
        HTTPException: 작업을 찾을 수 없거나 소유권이 다른 경우 404 Not Found 발생.
    """
    job = await sync_job_status_from_ml(job_id, db)
    if not job or job.user_id != user_id:
        log.warning(f"⚠️ 권한 없음 혹은 존재하지 않는 스캔 작업 조회 요청: Job ID={job_id}, User ID={user_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scan job not found")
    return ScanJobOut.model_validate(job)


async def get_scan_results(
    job_id: uuid.UUID,
    user_id: uuid.UUID,
    db: Session,
) -> list[ScanResultOut]:
    """완료된 스캔 작업의 상세 결과 리스트를 조회하며, 필요시 ML 서비스와 동기화합니다.

    Args:
        job_id (uuid.UUID): 조회할 작업의 고유 ID.
        user_id (uuid.UUID): 요청한 사용자의 고유 ID.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[ScanResultOut]: 스캔 결과 리스트.

    Raises:
        HTTPException: 작업을 찾을 수 없거나 소유권이 다른 경우 404 Not Found 발생.
    """
    job = await sync_job_status_from_ml(job_id, db)
    if not job or job.user_id != user_id:
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
