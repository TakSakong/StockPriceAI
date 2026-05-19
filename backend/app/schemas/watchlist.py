import uuid
from datetime import datetime

from pydantic import BaseModel


class WatchlistItemCreate(BaseModel):
    ticker: str
    memo: str | None = None


class WatchlistItemUpdate(BaseModel):
    memo: str | None = None


class WatchlistItemOut(BaseModel):
    id: uuid.UUID
    ticker: str
    memo: str | None
    added_at: datetime

    # N+1 해결을 위해 조인해 반환할 추가 주식 정보
    name: str | None = None
    sector: str | None = None
    industry: str | None = None
    market_cap: float | None = None
    current_price: float | None = None
    currency: str | None = None

    model_config = {"from_attributes": True}
