from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.forecast import Forecast
from app.schemas.forecast import ForecastOut
from app.services.daily_plan_service import get_daily_plan

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.get("/daily-plan")
def daily_plan(target_date: date | None = None, db: Session = Depends(get_db)) -> list[dict]:
    """Best hour-windows to work today, from historical averages (not the
    short-horizon ML model — see app/services/daily_plan_service.py)."""
    d = target_date or date.today()
    return get_daily_plan(db, d.weekday())


@router.get("", response_model=list[ForecastOut])
def list_forecasts(
    horizon_minutes: int = 30, district_id: int | None = None, db: Session = Depends(get_db)
) -> list[Forecast]:
    """Latest forecast per district for the given horizon."""
    stmt = select(Forecast).where(Forecast.horizon_minutes == horizon_minutes)
    if district_id is not None:
        stmt = stmt.where(Forecast.district_id == district_id)
    stmt = stmt.order_by(Forecast.district_id, Forecast.generated_at.desc())

    rows = db.execute(stmt).scalars().all()
    latest_by_district: dict[int, Forecast] = {}
    for f in rows:
        latest_by_district.setdefault(f.district_id, f)
    return list(latest_by_district.values())
