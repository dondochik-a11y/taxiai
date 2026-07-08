from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSource, pg_enum


class DemandSnapshot(Base):
    """Core demand-history time series: one row per (district, observed_at)."""

    __tablename__ = "demand_snapshots"
    __table_args__ = (Index("ix_demand_snapshots_district_time", "district_id", "observed_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    demand_level: Mapped[float] = mapped_column(Numeric(4, 3))  # 0..1
    surge_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=1.0)
    active_orders_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_drivers_estimate: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "demand_source"), default=DataSource.SYNTHETIC
    )
