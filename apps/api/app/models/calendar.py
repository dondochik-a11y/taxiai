from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import CalendarEventType, DataSource, ImpactLevel, pg_enum


class CalendarEvent(Base):
    __tablename__ = "calendar_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column(Date)
    event_type: Mapped[CalendarEventType] = mapped_column(pg_enum(CalendarEventType, "calendar_event_type"))
    title: Mapped[str] = mapped_column(String(255))
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="RESTRICT"), nullable=True
    )  # null = city-wide
    expected_impact: Mapped[ImpactLevel | None] = mapped_column(
        pg_enum(ImpactLevel, "impact_level"), nullable=True
    )

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "calendar_source"), default=DataSource.SYNTHETIC
    )
