import httpx
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.stock import StockInfo

router = APIRouter(prefix="/stocks", tags=["Stocks"])


@router.get("/{ticker}", response_model=StockInfo, summary="종목 기본 정보 조회")
async def get_stock(
    ticker: str,
) -> StockInfo:
    """ML 서비스에서 종목 기본 정보를 조회합니다."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{settings.ML_SERVICE_URL}/api/v1/technical/{ticker.upper()}")
            resp.raise_for_status()
            data = resp.json()
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

    return StockInfo(ticker=ticker.upper(), **data.get("info", {}))
