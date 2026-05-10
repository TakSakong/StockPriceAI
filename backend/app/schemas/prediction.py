import uuid
from datetime import datetime

from pydantic import BaseModel


class PredictionOut(BaseModel):
    id: uuid.UUID
    ticker: str
    signal: str
    up_prob: float
    model_type: str | None
    complexity: float | None
    xgb_weight: float | None
    lstm_weight: float | None
    created_at: datetime

    model_config = {"from_attributes": True}
