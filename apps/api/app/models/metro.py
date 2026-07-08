from datetime import datetime

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSource, MetroIncidentType, pg_enum


class MetroIncident(Base):
    __tablename__ = "metro_incidents"

    id: Mapped[int] = mapped_column(primary_key=True)
    line_name: Mapped[str] = mapped_column(String(64))
    station_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    incident_type: Mapped[MetroIncidentType] = mapped_column(pg_enum(MetroIncidentType, "metro_incident_type"))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "metro_source"), default=DataSource.SYNTHETIC
    )
