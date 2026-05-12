
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.user import User
from app.models.watchlist import WatchlistItem
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemOut, WatchlistItemUpdate
from app.services.auth import get_current_user

router = APIRouter(prefix="/watchlist", tags=["Watchlist"])


@router.get("", response_model=list[WatchlistItemOut], summary="관심종목 목록 조회")
def list_watchlist(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[WatchlistItemOut]:
    """현재 로그인한 사용자의 모든 관심 종목 리스트를 조회합니다.

    Args:
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        list[WatchlistItemOut]: 관심 종목 모델 리스트.
    """
    items = db.query(WatchlistItem).filter(WatchlistItem.user_id == current_user.id).all()
    return [WatchlistItemOut.model_validate(i) for i in items]


@router.post("", response_model=WatchlistItemOut, status_code=201, summary="관심종목 추가")
def add_watchlist(
    payload: WatchlistItemCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WatchlistItemOut:
    """새로운 종목을 사용자의 관심 종목 리스트에 추가합니다.

    중복 등록 여부를 확인한 후, 티커와 메모를 저장합니다.

    Args:
        payload (WatchlistItemCreate): 추가할 종목 정보 (ticker, memo).
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        WatchlistItemOut: 추가된 관심 종목 정보.

    Raises:
        HTTPException: 이미 리스트에 존재하는 종목인 경우 409 Conflict 발생.
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
    return WatchlistItemOut.model_validate(item)


@router.patch("/{ticker}", response_model=WatchlistItemOut, summary="관심종목 메모 수정")
def update_watchlist_item(
    ticker: str,
    payload: WatchlistItemUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> WatchlistItemOut:
    """특정 관심 종목의 메모를 수정합니다.

    Args:
        ticker (str): 수정할 종목 코드.
        payload (WatchlistItemUpdate): 수정할 메모 내용.
        current_user (User): 인증된 현재 사용자.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        WatchlistItemOut: 수정된 관심 종목 정보.

    Raises:
        HTTPException: 관심 종목 리스트에 해당 종목이 없는 경우 404 Not Found 발생.
    """
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
    return WatchlistItemOut.model_validate(item)


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
