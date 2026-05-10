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
