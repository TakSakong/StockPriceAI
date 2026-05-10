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

    model_config = {"from_attributes": True}
