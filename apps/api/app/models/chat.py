import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import ChatRole, pg_enum


class ChatMessage(Base):
    """Simple conversation history for the AI chat assistant — no RAG/vector DB at this scale."""

    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    role: Mapped[ChatRole] = mapped_column(pg_enum(ChatRole, "chat_role"))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
