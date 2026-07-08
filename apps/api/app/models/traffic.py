from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSource, pg_enum


class TrafficObservation(Base):
    __tablename__ = "traffic_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))

    congestion_level: Mapped[float] = mapped_column(Numeric(3, 1))  # 0..10, "Yandex ball" style
    avg_speed_kmh: Mapped[float | None] = mapped_column(Numeric(5, 1), nullable=True)

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "traffic_source"), default=DataSource.SYNTHETIC
    )
