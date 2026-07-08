import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, SmallInteger, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.models.enums import DeliveryChannel, RecommendationAction, pg_enum


class Recommendation(Base):
    __tablename__ = "recommendations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE")
    )
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    current_district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))
    recommended_district_id: Mapped[int] = mapped_column(ForeignKey("districts.id", ondelete="RESTRICT"))
    recommended_horizon_minutes: Mapped[int] = mapped_column(SmallInteger)
    action: Mapped[RecommendationAction] = mapped_column(pg_enum(RecommendationAction, "recommendation_action"))
    probability: Mapped[float] = mapped_column(Numeric(4, 3))

    expected_avg_check: Mapped[float] = mapped_column(Numeric(8, 2))
    rationale_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    delivered_via: Mapped[DeliveryChannel] = mapped_column(
        pg_enum(DeliveryChannel, "delivery_channel"), default=DeliveryChannel.WEB
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
