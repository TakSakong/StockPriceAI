from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.prediction import Prediction
from app.models.user import User
from app.schemas.prediction import PredictionOut
from app.services.auth import get_current_user

router = APIRouter(prefix="/predictions", tags=["Predictions"])


@router.get("/{ticker}", response_model=list[PredictionOut], summary="종목 예측 이력 조회")
def get_predictions(
    ticker: str,
    limit: int = Query(default=10, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PredictionOut]:
    """특정 종목(ticker)에 대한 최근 예측 이력을 조회합니다.

    데이터베이스에서 해당 티커의 예측 결과를 생성일자 내림차순으로 조회하여 반환합니다.

    Args:
        ticker (str): 조회할 종목 코드 (예: AAPL, TSLA).
        limit (int): 최대 조회 개수 (1~100, 기본값 10).
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[PredictionOut]: 예측 이력 리스트.

    Raises:
        HTTPException: 해당 종목의 예측 이력이 없는 경우 404 Not Found 발생.
    """
    rows = (
        db.query(Prediction)
        .filter(Prediction.ticker == ticker.upper())
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )
    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No predictions found for ticker")
    return [PredictionOut.model_validate(r) for r in rows]
