from fastapi import APIRouter

from app.schemas.stock import StockInfo
from app.services.stock import fetch_stock_info

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
    return await fetch_stock_info(ticker)
