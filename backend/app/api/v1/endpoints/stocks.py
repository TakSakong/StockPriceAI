import httpx
from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.schemas.stock import StockInfo

router = APIRouter(prefix="/stocks", tags=["Stocks"])


@router.get("/{ticker}", response_model=StockInfo, summary="종목 기본 정보 조회")
async def get_stock(
    ticker: str,
) -> StockInfo:
    """ML 서비스를 통해 특정 종목의 실시간 기본 정보 및 기술적 지표를 조회합니다.

    Args:
        ticker (str): 조회할 종목 코드 (예: AAPL).

    Returns:
        StockInfo: 종목명, 현재가, 시가총액, 기술적 지표 등을 포함한 상세 정보.

    Raises:
        HTTPException: 
            - ML 서비스에서 데이터를 찾을 수 없는 경우 (404)
            - ML 서비스가 응답하지 않는 경우 (503)
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # ml service 호출해서 ticker 정보를 받는다.
            resp = await client.get(f"{settings.ML_SERVICE_URL}/api/v1/technical/{ticker.upper()}")
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            # ML 서비스가 데이터를 찾지 못하는 경우(404) 기본 정보라도 반환하여 프론트엔드 오류 방지
            if e.response.status_code == 404:
                return StockInfo(
                    ticker=ticker.upper(),
                    name=ticker.upper(),
                    current_price=None
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
    # ML 서비스가 현재 info 필드를 제공하지 않으므로, 최신 지표 데이터를 바탕으로 StockInfo 생성
    return StockInfo(
        ticker=ticker.upper(),
        name=ticker.upper(), # 종목명을 알 수 없으므로 우선 티커로 대체
        current_price=indicators.get("close"),
    )
