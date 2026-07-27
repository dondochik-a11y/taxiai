from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ModelMetric(Base):
    """One row per demand-model retrain: the holdout evaluation that used to be
    printed and lost to the log. Persisting it turns forecast quality into a
    queryable history — you can see whether MAE crept up, and (with trained_at)
    whether the weekly retrain is actually running. The staleness watchdog and
    the operator /health surface both read the latest row here.

    Written by app/ml/train_demand_model.py right after the holdout eval;
    never updated in place."""

    __tablename__ = "model_metrics"
    __table_args__ = (Index("ix_model_metrics_trained_at", "trained_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    model_version: Mapped[str] = mapped_column(String(64))

    holdout_mae: Mapped[float | None] = mapped_column(Numeric(6, 4), nullable=True)
    # {"15": 0.12, "30": 0.15, "60": 0.19, "120": 0.24} — MAE per forecast horizon.
    mae_by_horizon: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    train_rows: Mapped[int] = mapped_column(Integer)
    holdout_rows: Mapped[int] = mapped_column(Integer)
