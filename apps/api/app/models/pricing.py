from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String

from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSource, pg_enum


class PriceObservation(Base):
    """One real (or synthetic) ride-price quote for a district's reference
    route. The surge coefficient is NOT stored — it is derived at read time as
    price / rolling-baseline (see app/services/surge_service.py), so early
    observations don't freeze a wrong baseline into the data."""

    __tablename__ = "price_observations"
    __table_args__ = (
        Index("ix_price_observations_district_observed", "district_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))

    tariff_class: Mapped[str] = mapped_column(String(32), default="econom")
    price: Mapped[float] = mapped_column(Numeric(8, 2))
    currency: Mapped[str] = mapped_column(String(8), default="RUB")

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "price_source"), default=DataSource.LIVE
    )
