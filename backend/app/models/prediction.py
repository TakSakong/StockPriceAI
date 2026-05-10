import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Prediction(Base):
    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticker: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    signal: Mapped[str] = mapped_column(String(10), nullable=False)
    up_prob: Mapped[float] = mapped_column(Float, nullable=False)
    model_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    complexity: Mapped[float | None] = mapped_column(Float, nullable=True)
    xgb_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    lstm_weight: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
