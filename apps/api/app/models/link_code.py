from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LinkCode(Base):
    """Short-lived one-time code that ties a Telegram account and a web account
    to the same user row. Whichever side has a user_id generates the code; the
    other side redeems it (see app/services/link_service.py). Expired/used rows
    are pruned opportunistically on the next generate for the same user."""

    __tablename__ = "link_codes"

    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
