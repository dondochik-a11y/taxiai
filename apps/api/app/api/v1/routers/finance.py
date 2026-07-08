import uuid
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.finance import FinanceSummaryOut
from app.services.finance_service import compute_daily_summary

router = APIRouter(prefix="/finance", tags=["finance"])


@router.get("/daily-summary", response_model=FinanceSummaryOut)
def daily_summary(
    user_id: uuid.UUID, summary_date: date | None = None, db: Session = Depends(get_db)
) -> FinanceSummaryOut:
    target_date = summary_date or date.today()
    return compute_daily_summary(db, user_id, target_date)
