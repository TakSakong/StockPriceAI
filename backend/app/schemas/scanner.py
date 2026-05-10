import uuid
from datetime import datetime

from pydantic import BaseModel


class ScanJobCreate(BaseModel):
    sector: str | None = None


class ScanJobOut(BaseModel):
    id: uuid.UUID
    status: str
    total: int | None
    processed: int
    sector: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScanResultOut(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    ticker: str
    composite_score: float | None
    up_prob: float | None
    signal: str | None
    sector: str | None
    est_upside: float | None
    cached_at: datetime

    model_config = {"from_attributes": True}
