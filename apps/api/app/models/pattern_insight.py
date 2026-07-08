from datetime import datetime

from sqlalchemy import DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PatternInsight(Base):
    """Output of the pattern-mining job — e.g. 'rain + Paveletskaya = +27% income'."""

    __tablename__ = "pattern_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    pattern_text: Mapped[str] = mapped_column(Text)
    condition_json: Mapped[dict] = mapped_column(JSONB)  # e.g. {"weather": "rain", "district": "Paveletskaya"}
    effect_metric: Mapped[str] = mapped_column(String(64))  # e.g. 'income_per_hour'
    effect_magnitude_pct: Mapped[float] = mapped_column(Numeric(6, 2))
    confidence: Mapped[float] = mapped_column(Numeric(4, 3))
    sample_size: Mapped[int] = mapped_column(Integer)

    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
