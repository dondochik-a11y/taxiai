import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import NotificationType, pg_enum


class TelegramNotificationLog(Base):
    """Dedup log so the bot's polling loop doesn't resend the same morning
    plan / pre-shift alert / post-shift summary more than once per day. This
    is an at-most-once send: a row is written the moment the API includes a
    notification in a pending-notifications response, not after the bot
    confirms delivery — a reasonable MVP simplification over building a full
    ack protocol."""

    __tablename__ = "telegram_notification_log"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "notification_type", "notification_date", name="uq_notification_user_type_date"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    notification_type: Mapped[NotificationType] = mapped_column(
        pg_enum(NotificationType, "notification_type")
    )
    notification_date: Mapped[date] = mapped_column(Date)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
