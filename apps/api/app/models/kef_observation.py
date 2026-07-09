from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DataSource, pg_enum


class KefObservation(Base):
    """One surge-coefficient reading lifted from a driver's kef-radar screenshot
    (e.g. "Радар кэфа"). Raw and deliberately loose: the kef itself is trusted,
    but district_id is often unknown — a screenshot carries no map bounds, so
    geo-referencing is best-effort (area_hint holds the nearest OCR'd map label).

    Kept SEPARATE from the clean demand_snapshots training table so imprecise
    readings never silently pollute it — mirroring price_observations. A later
    ETL step promotes trustworthy rows (known district, sane kef) into
    demand_snapshots with source=RADAR."""

    __tablename__ = "kef_observations"
    __table_args__ = (
        Index("ix_kef_observations_observed", "observed_at"),
        Index("ix_kef_observations_district_observed", "district_id", "observed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Radar bubbles show a range (e.g. 1.18–1.56). Single-value reads set both equal.
    kef_min: Mapped[float] = mapped_column(Numeric(4, 2))
    kef_max: Mapped[float] = mapped_column(Numeric(4, 2))

    tariff_class: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Best-effort geo. district_id nullable on purpose (no map bounds in a screenshot).
    district_id: Mapped[int | None] = mapped_column(
        ForeignKey("districts.id", ondelete="SET NULL"), nullable=True
    )
    area_hint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    lat: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)
    lng: Mapped[float | None] = mapped_column(Numeric(9, 6), nullable=True)

    # Who forwarded it, plus the full OCR text for audit / later reprocessing.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[DataSource] = mapped_column(
        pg_enum(DataSource, "kef_source"), default=DataSource.RADAR
    )
