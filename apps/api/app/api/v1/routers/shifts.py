import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.shift import ShiftToggleOut
from app.services.finance_service import compute_daily_summary
from app.services.shift_service import toggle_shift

router = APIRouter(prefix="/shifts", tags=["shifts"])


@router.post("/toggle", response_model=ShiftToggleOut)
def toggle(user_id: uuid.UUID, db: Session = Depends(get_db)) -> ShiftToggleOut:
    """Start a shift if none is open for this driver, otherwise stop the open
    one. The start/stop decision is server-side; on stop we also recompute
    today's summary (now using the real shift end) so the bot can show elapsed
    time + income earned. Mirrors the thin-bot design of the /alert flow."""
    now = datetime.now(timezone.utc)
    result = toggle_shift(db, user_id, now=now)

    if result["action"] == "stopped":
        summary = compute_daily_summary(db, user_id, now.date())
        result["net_income_today"] = float(summary.net_income)
        result["gross_income_today"] = float(summary.gross_income)
        result["trips_count_today"] = int(summary.trips_count)

    return ShiftToggleOut(**result)
