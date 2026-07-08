from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSource, PrecipitationType, pg_enum


class WeatherObservation(Base):
    __tablename__ = "weather_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="RESTRICT"), nullable=True
    )  # null = city-wide reading

    temperature_c: Mapped[float] = mapped_column(Numeric(4, 1))
    precipitation_type: Mapped[PrecipitationType] = mapped_column(
        pg_enum(PrecipitationType, "precipitation_type"), default=PrecipitationType.NONE
    )
    precipitation_mm: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    wind_speed_ms: Mapped[float] = mapped_column(Numeric(4, 1), default=0)
    condition_text: Mapped[str | None] = mapped_column(String(64), nullable=True)

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "weather_source"), default=DataSource.SYNTHETIC
    )
