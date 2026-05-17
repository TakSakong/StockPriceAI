import logging
from typing import Any

import httpx
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.prediction import Prediction
from app.schemas.prediction import PredictionOut

log = logging.getLogger("stockai.backend.prediction")


async def get_or_fetch_predictions(
    ticker: str,
    limit: int,
    db: Session,
) -> list[PredictionOut]:
    """DB에서 예측 이력을 조회하고, 없으면 ML 서비스에 예측을 요청하여 저장 후 반환합니다.

    1. DB에 해당 티커의 예측 이력이 있으면 그대로 반환합니다.
    2. DB에 없으면 ML 서비스의 /api/v1/predict 엔드포인트를 호출합니다.
    3. ML 응답을 Prediction 모델로 변환하여 DB에 저장하고 반환합니다.

    Args:
        ticker (str): 조회할 종목 코드 (예: AAPL).
        limit (int): 최대 조회 개수.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[PredictionOut]: 예측 결과 리스트.

    Raises:
        HTTPException:
            - ML 서비스가 응답하지 않는 경우 (503)
            - ML 서비스에서 데이터를 찾을 수 없는 경우 (404)
    """
    # 1. DB 조회
    rows = (
        db.query(Prediction)
        .filter(Prediction.ticker == ticker.upper())
        .order_by(Prediction.created_at.desc())
        .limit(limit)
        .all()
    )
    if rows:
        return [PredictionOut.model_validate(r) for r in rows]

    # 2. DB에 없으면 ML 서비스에 예측 요청
    log.info(f"DB에 예측 없음 → ML 서비스 호출: {ticker}")
    ml_result = await _call_ml_predict(ticker)

    # 3. ML 응답을 DB에 저장
    ensemble_detail = ml_result.get("ensemble_detail") or {}
    new_prediction = Prediction(
        ticker=ticker.upper(),
        signal=ml_result["signal"],
        up_prob=ml_result["up_probability"],
        model_type=ml_result.get("model"),
        complexity=ensemble_detail.get("complexity"),
        xgb_weight=ensemble_detail.get("w_xgb"),
        lstm_weight=ensemble_detail.get("w_lstm"),
    )
    db.add(new_prediction)
    db.commit()
    db.refresh(new_prediction)

    log.info(f"ML 예측 결과 DB 저장 완료: {ticker} → {new_prediction.signal}")
    return [PredictionOut.model_validate(new_prediction)]


async def _call_ml_predict(ticker: str) -> dict[str, Any]:
    """ML 서비스의 /api/v1/predict 엔드포인트를 호출하여 예측 결과를 반환합니다.

    Args:
        ticker (str): 조회할 종목 코드.

    Returns:
        dict: ML 서비스의 예측 응답 JSON.

    Raises:
        HTTPException:
            - ML 서비스가 응답하지 않는 경우 (503)
            - ML 서비스에서 404를 반환한 경우 (404)
    """
    async with httpx.AsyncClient(timeout=120.0) as client:  # ML 예측은 시간이 걸림
        try:
            resp = await client.post(
                f"{settings.ML_SERVICE_URL}/api/v1/predict",
                json={"ticker": ticker.upper()},
            )
            resp.raise_for_status()
            result: dict[str, Any] = resp.json()
            return result
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"ML service error: {e.response.text}",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ML service unavailable",
            )
