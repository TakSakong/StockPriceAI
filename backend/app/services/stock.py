import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.schemas.stock import StockInfo


async def fetch_stock_info(ticker: str) -> StockInfo:
    """ML 서비스에서 종목 정보를 조회하여 StockInfo로 반환합니다.

    ML 서비스의 /api/v1/technical/{ticker} 엔드포인트를 호출하고,
    응답 데이터를 StockInfo 스키마에 맞게 변환합니다.

    Args:
        ticker (str): 조회할 종목 코드 (예: AAPL).

    Returns:
        StockInfo: 종목 기본 정보 및 현재 가격.

    Raises:
        HTTPException:
            - ML 서비스에서 데이터를 찾을 수 없는 경우 (404)
            - ML 서비스가 응답하지 않는 경우 (503)
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{settings.ML_SERVICE_URL}/api/v1/technical/{ticker.upper()}"
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            # ML 서비스가 데이터를 찾지 못하는 경우(404) 기본 정보 반환
            if e.response.status_code == 404:
                return StockInfo(
                    ticker=ticker.upper(),
                    name=ticker.upper(),
                    current_price=None,
                )
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"ML service error: {e.response.text}",
            )
        except httpx.RequestError:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="ML service unavailable",
            )

    indicators = data.get("latest_indicators", {})
    return StockInfo(
        ticker=ticker.upper(),
        name=ticker.upper(),  # ML 서비스가 종목명을 제공하지 않아 티커로 대체
        current_price=indicators.get("close"),
        marcket_cap=data.get("market_cap", 0),
        sector=data.get("sector", "Unknown"),
    )
