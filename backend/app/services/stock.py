import json
import httpx
from fastapi import HTTPException, status

from app.core.config import settings
from app.core.redis import redis_client
from app.schemas.stock import StockInfo


async def fetch_stock_info(ticker: str) -> StockInfo:
    """ML 서비스에서 종목 정보를 조회하여 StockInfo로 반환합니다.

    ML 서비스의 /api/v1/technical/{ticker} 엔드포인트를 호출하고,
    부족한 회사 기본 정보는 ML이 저장한 Redis(fetcher:stock)에서 보완합니다.
    """
    ticker_upper = ticker.upper().strip()

    # 1. 무조건 ML 서비스에 요청을 보내 최신 기술적 지표 계산 (및 ML Redis 캐시 갱신 유도)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                f"{settings.ML_SERVICE_URL}/api/v1/technical/{ticker_upper}"
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return StockInfo(
                    ticker=ticker_upper,
                    name=ticker_upper,
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

    # 2. ML 응답에서 기술적 지표 추출
    indicators = data.get("latest_indicators", {})

    # 3. ML 서비스가 저장한 원본 Redis 캐시에서 부족한 기본 정보(info) 가져오기
    normalized_ticker = ticker_upper
    if ticker_upper.isdigit() and len(ticker_upper) == 6:
        normalized_ticker = f"{ticker_upper}.KS"
    
    cache_key = f"fetcher:stock:{normalized_ticker}"
    
    info = {}
    try:
        cached_data = await redis_client.get(cache_key)
        if cached_data:
            cache_payload = json.loads(cached_data)
            info = cache_payload.get("info", {})
    except Exception as e:
        print(f"DEBUG: [REDIS INFO ERROR] {str(e)}")

    # 4. 최종 데이터 조합 반환
    return StockInfo(
        ticker=ticker_upper,
        name=info.get("longName") or info.get("shortName") or ticker_upper,
        current_price=indicators.get("close"),
        market_cap=info.get("marketCap") or 0,
        sector=info.get("sector") or "Unknown",
    )
