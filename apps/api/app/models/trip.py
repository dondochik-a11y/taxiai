import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSource, pg_enum


class Trip(Base):
    __tablename__ = "trips"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )

    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    start_district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))
    end_district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))

    start_lat: Mapped[float] = mapped_column(Numeric(9, 6))
    start_lng: Mapped[float] = mapped_column(Numeric(9, 6))
    end_lat: Mapped[float] = mapped_column(Numeric(9, 6))
    end_lng: Mapped[float] = mapped_column(Numeric(9, 6))

    time_to_pickup_seconds: Mapped[int] = mapped_column(Integer)
    wait_time_seconds: Mapped[int] = mapped_column(Integer)
    distance_km: Mapped[float] = mapped_column(Numeric(6, 2))
    duration_seconds: Mapped[int] = mapped_column(Integer)

    price: Mapped[float] = mapped_column(Numeric(8, 2))
    tariff: Mapped[str] = mapped_column(String(32))
    surge_multiplier_at_start: Mapped[float | None] = mapped_column(Numeric(4, 2), nullable=True)

    weather_id: Mapped[int | None] = mapped_column(
        ForeignKey("weather_observations.id", ondelete="SET NULL"), nullable=True
    )

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "trip_source"), default=DataSource.SYNTHETIC
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
