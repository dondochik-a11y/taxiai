"""Model-health readout: the latest persisted retrain metrics plus a computed
age and staleness verdict. Backs both the operator /health surface (via the API
router) and the worker's staleness watchdog, so the "is the model fresh?"
question is answered the same way in both places."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.model_metrics import ModelMetric
from app.services import monitoring

# Same artifact train_demand_model.py writes. Kept as a literal path here rather
# than imported so the API/health surface doesn't pull scikit-learn into its
# import graph just to stat a file.
MODEL_PATH = Path(__file__).resolve().parents[1] / "ml" / "artifacts" / "demand_model.joblib"


def _artifact_mtime() -> datetime | None:
    """Fallback freshness signal when no model_metrics row exists yet (e.g. a
    model trained before this table landed): the artifact file's mtime."""
    try:
        return datetime.fromtimestamp(MODEL_PATH.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def get_model_health(session: Session, now: datetime | None = None) -> dict:
    """Latest model metrics + age + staleness. `trained_at` falls back to the
    artifact mtime, then to None (no model at all — treated as stale)."""
    now = now or datetime.now(timezone.utc)
    row = session.execute(
        select(ModelMetric).order_by(ModelMetric.trained_at.desc()).limit(1)
    ).scalar_one_or_none()

    if row is not None:
        trained_at = row.trained_at
        metrics = {
            "model_version": row.model_version,
            "holdout_mae": float(row.holdout_mae) if row.holdout_mae is not None else None,
            "mae_by_horizon": row.mae_by_horizon or {},
            "train_rows": row.train_rows,
            "holdout_rows": row.holdout_rows,
        }
    else:
        trained_at = _artifact_mtime()
        metrics = {
            "model_version": None,
            "holdout_mae": None,
            "mae_by_horizon": {},
            "train_rows": None,
            "holdout_rows": None,
        }

    if trained_at is not None and trained_at.tzinfo is None:
        trained_at = trained_at.replace(tzinfo=timezone.utc)

    age_seconds = (now - trained_at).total_seconds() if trained_at is not None else None
    return {
        "trained_at": trained_at.isoformat() if trained_at is not None else None,
        "age_hours": round(age_seconds / 3600, 1) if age_seconds is not None else None,
        "age_days": round(age_seconds / 86400, 1) if age_seconds is not None else None,
        "is_stale": monitoring.is_model_stale(trained_at, now),
        "stale_threshold_days": monitoring.MODEL_STALE_AFTER.days,
        **metrics,
    }
