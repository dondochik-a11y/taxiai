from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric, SmallInteger, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Forecast(Base):
    """Model output cache: one row per (district, generated_at, horizon_minutes)."""

    __tablename__ = "forecasts"
    __table_args__ = (
        Index("ix_forecasts_district_generated_horizon", "district_id", "generated_at", "horizon_minutes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    horizon_minutes: Mapped[int] = mapped_column(SmallInteger)  # 15/30/60/120
    target_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    predicted_demand_level: Mapped[float] = mapped_column(Numeric(4, 3))
    predicted_surge: Mapped[float] = mapped_column(Numeric(4, 2))
    predicted_avg_check: Mapped[float] = mapped_column(Numeric(8, 2))
    predicted_wait_time_seconds: Mapped[int] = mapped_column(Integer)

    model_version: Mapped[str] = mapped_column(String(64))
