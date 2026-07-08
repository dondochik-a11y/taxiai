from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.surge import SurgeNowOut
from app.services.surge_service import get_current_surge

router = APIRouter(prefix="/surge", tags=["surge"])


@router.get("/current", response_model=list[SurgeNowOut])
def current_surge(db: Session = Depends(get_db)) -> list[dict]:
    """Current surge coefficient per district: real (from Yandex Taxi prices)
    where fresh live quotes exist, synthetic-feed fallback elsewhere."""
    return get_current_surge(db)
