import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AiTripAnalysis(Base):
    """GPT (or mock-template) post-mortem attached to a single trip."""

    __tablename__ = "ai_trip_analyses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    trip_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("trips.id", ondelete="CASCADE"), unique=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )

    summary_text: Mapped[str] = mapped_column(Text)
    estimated_missed_earnings: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    suggested_action: Mapped[str | None] = mapped_column(Text, nullable=True)

    model_used: Mapped[str] = mapped_column(String(64))  # e.g. 'mock-template-v1' or 'gpt-4o-mini'
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
