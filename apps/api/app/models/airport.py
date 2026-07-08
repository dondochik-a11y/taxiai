from datetime import datetime

from sqlalchemy import DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import AirportCode, DataSource, FlightDirection, FlightStatus, pg_enum


class AirportFlight(Base):
    __tablename__ = "airport_flights"

    id: Mapped[int] = mapped_column(primary_key=True)
    airport_code: Mapped[AirportCode] = mapped_column(pg_enum(AirportCode, "airport_code"))
    scheduled_time: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    actual_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    direction: Mapped[FlightDirection] = mapped_column(pg_enum(FlightDirection, "flight_direction"))
    status: Mapped[FlightStatus] = mapped_column(
        pg_enum(FlightStatus, "flight_status"), default=FlightStatus.ON_TIME
    )
    delay_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "airport_source"), default=DataSource.SYNTHETIC
    )
