import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Shift(Base):
    """A real work-shift boundary, started/stopped from the bot's /shift toggle.

    Replaces the old "online hours = span between the day's first and last trip"
    inference in finance_service: with an explicit shift the ₽/hour figure stops
    counting a two-hour lunch break as if the driver were online. Exactly one row
    per (driver, shift); the currently-open shift is the single row with
    ended_at IS NULL (the toggle enforces at-most-one-open per driver)."""

    __tablename__ = "shifts"
    __table_args__ = (
        # Fast "is there an open shift?" and "shifts overlapping this day" lookups.
        Index("ix_shifts_user_started", "user_id", "started_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
