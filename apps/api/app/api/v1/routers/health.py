from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services.health_service import get_model_health

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/model")
def model_health(db: Session = Depends(get_db)) -> dict:
    """Operator readout: latest demand-model retrain metrics (version,
    trained_at/age, holdout + per-horizon MAE) and whether it's gone stale.
    Backs the bot /health command; also handy for a manual curl."""
    return get_model_health(db)
