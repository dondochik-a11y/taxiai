import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProximitySurgeAlertLog(Base):
    """Cooldown log for the proactive «рядом скачок спроса» push. Unlike the
    once/day telegram_notification_log (keyed on user+type+date), this throttles
    per (driver, district) on a short rolling window (see
    app/services/alerts.py PROXIMITY_COOLDOWN): a real second spike later the
    same day can alert again, but one lingering spike won't fire every poll
    tick. A row is written the moment the API includes the alert in a
    pending-notifications response (at-most-once, matching the log's MVP
    simplification)."""

    __tablename__ = "proximity_surge_alert_log"
    __table_args__ = (
        Index("ix_proximity_alert_user_district_sent", "user_id", "district_id", "sent_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="CASCADE"))
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
