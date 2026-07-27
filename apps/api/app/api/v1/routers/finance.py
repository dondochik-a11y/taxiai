import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.finance import FinanceSummaryOut, WeeklySummaryOut
from app.services.finance_service import (
    WEEKLY_DEFAULT_DAYS,
    compute_daily_summary,
    compute_weekly_summary,
)

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/daily-summary", response_model=FinanceSummaryOut)
def daily_summary(
    user_id: uuid.UUID, summary_date: date | None = None, db: Session = Depends(get_db)
) -> FinanceSummaryOut:
    target_date = summary_date or date.today()
    return compute_daily_summary(db, user_id, target_date)


@router.get("/weekly-summary/{user_id}", response_model=WeeklySummaryOut)
def weekly_summary(
    user_id: uuid.UUID,
    days: int = Query(WEEKLY_DEFAULT_DAYS, ge=1, le=31),
    end_date: date | None = None,
    db: Session = Depends(get_db),
) -> WeeklySummaryOut:
    """One response with `days` (default 14) of daily figures + totals — the
    finance dashboard's single call in place of N per-day /daily-summary calls."""
    end = end_date or date.today()
    return compute_weekly_summary(db, user_id, end, days)
