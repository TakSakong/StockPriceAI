
import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemOut, WatchlistItemUpdate
from app.services.auth import get_current_user
from app.services.stock import get_ml_redis_client

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=list[WatchlistItemOut], summary="관심종목 목록 조회")
async def list_watchlist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WatchlistItemOut]:
    """현재 로그인한 사용자의 모든 관심 종목 리스트를 조회합니다.

    [N+1 해결 최적화 - Redis Bulk Pipeline Join]
    관심종목 목록 조회 시 각 종목의 메타데이터(이름, 가격, 섹터 등)를 
    Redis Pipeline을 사용하여 단 1회의 네트워크 호출로 가져와 조인하여 반환합니다.
    """
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == current_user.id).all()
    if not items:
        return []

    # Redis Pipeline을 통해 한 번에 캐시 데이터 벌크 조회
    r = get_ml_redis_client()
    pipe = r.pipeline()
    
    for item in items:
        ticker_upper = item.ticker.upper().strip()
        normalized_ticker = ticker_upper
        if ticker_upper.isdigit() and len(ticker_upper) == 6:
            normalized_ticker = f"{ticker_upper}.KS"
        cache_key = f"fetcher:stock:{normalized_ticker}"
        pipe.get(cache_key)
        
    try:
        cached_results = await pipe.execute()
    except Exception:
        cached_results = [None] * len(items)

    response_items = []
    for item, cached_data in zip(items, cached_results):
        out = WatchlistItemOut(
            id=item.id,
            ticker=item.ticker,
            memo=item.memo,
            added_at=item.added_at,
        )
        
        # 캐시 데이터가 존재하는 경우 메타데이터 파싱 및 조인
        if cached_data:
            try:
                payload = json.loads(cached_data)
                info = payload.get("info", {})
                history = payload.get("history", [])
                
                cached_price = None
                if history:
                    cached_price = history[-1].get("Close")
                    
                out.name = info.get("longName") or info.get("shortName") or item.ticker
                out.sector = info.get("sector") or "Unknown"
                out.industry = info.get("industry") or "Unknown"
                out.market_cap = info.get("marketCap") or 0.0
                out.current_price = cached_price
                out.currency = info.get("currency") or "USD"
            except Exception:
                pass
                
        response_items.append(out)
        
    return response_items


async def _enrich_watchlist_item(item: WatchlistItem) -> WatchlistItemOut:
    """단일 관심종목의 메타데이터를 Redis 캐시에서 동적으로 조회하여 조인합니다."""
    out = WatchlistItemOut(
        id=item.id,
        ticker=item.ticker,
        memo=item.memo,
        added_at=item.added_at,
    )
    
    r = get_ml_redis_client()
    ticker_upper = item.ticker.upper().strip()
    normalized_ticker = ticker_upper
    if ticker_upper.isdigit() and len(ticker_upper) == 6:
        normalized_ticker = f"{ticker_upper}.KS"
    cache_key = f"fetcher:stock:{normalized_ticker}"
    
    try:
        cached_data = await r.get(cache_key)
        if cached_data:
            payload = json.loads(cached_data)
            info = payload.get("info", {})
            history = payload.get("history", [])
            
            cached_price = None
            if history:
                cached_price = history[-1].get("Close")
                
            out.name = info.get("longName") or info.get("shortName") or item.ticker
            out.sector = info.get("sector") or "Unknown"
            out.industry = info.get("industry") or "Unknown"
            out.market_cap = info.get("marketCap") or 0.0
            out.current_price = cached_price
            out.currency = info.get("currency") or "USD"
    except Exception:
        pass
        
    return out


@router.post("", response_model=WatchlistItemOut, status_code=201, summary="관심종목 추가")
async def add_watchlist(
    payload: WatchlistItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WatchlistItemOut:
    """새로운 종목을 사용자의 관심 종목 리스트에 추가합니다.

    중복 등록 여부를 확인한 후, 티커와 메모를 저장합니다.
    """
    existing = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id, WatchlistItem.ticker == payload.ticker.upper())
        .first()
    )
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ticker already in watchlist")

    item = WatchlistItem(
        user_id=current_user.id,
        ticker=payload.ticker.upper(),
        memo=payload.memo,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return await _enrich_watchlist_item(item)


@router.patch("/{ticker}", response_model=WatchlistItemOut, summary="관심종목 메모 수정")
async def update_watchlist_item(
    ticker: str,
    payload: WatchlistItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WatchlistItemOut:
    """특정 관심 종목의 메모를 수정합니다."""
    item = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id, WatchlistItem.ticker == ticker.upper())
        .first()
    )
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not in watchlist")
    item.memo = payload.memo
    db.commit()
    db.refresh(item)
    return await _enrich_watchlist_item(item)


@router.delete("/{ticker}", status_code=204, summary="관심종목 삭제")
def delete_watchlist_item(
    ticker: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    """관심 종목 리스트에서 특정 종목을 제거합니다.

    Args:
        ticker (str): 삭제할 종목 코드.
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Raises:
        HTTPException: 관심 종목 리스트에 해당 종목이 없는 경우 404 Not Found 발생.
    """
    deleted = (
        db.query(WatchlistItem)
        .filter(WatchlistItem.user_id == current_user.id, WatchlistItem.ticker == ticker.upper())
        .delete()
    )
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ticker not in watchlist")
    db.commit()
