from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.schemas.prediction import PredictionOut
from app.services.auth import get_current_user
from app.services.prediction import get_or_fetch_predictions

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.get("/{ticker}", response_model=list[PredictionOut], summary="종목 예측 이력 조회")
async def get_predictions(
    ticker: str,
    limit: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PredictionOut]:
    """특정 종목(ticker)에 대한 최근 예측 이력을 조회합니다.

    DB에 이력이 있으면 반환하고, 없으면 ML 서비스에 예측을 요청한 뒤
    결과를 DB에 저장하고 반환합니다.

    Args:
        ticker (str): 조회할 종목 코드 (예: AAPL, TSLA).
        limit (int): 최대 조회 개수 (1~100, 기본값 10).
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[PredictionOut]: 예측 이력 리스트.

    Raises:
        HTTPException:
            - ML 서비스가 응답하지 않는 경우 (503)
            - ML 서비스에서 데이터를 찾을 수 없는 경우 (404)
    """
    return await get_or_fetch_predictions(ticker=ticker, limit=limit, db=db)
