import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.finance import Expense
from app.schemas.finance import (
    ExpenseCreate,
    ExpenseOut,
    FinanceSummaryOut,
    WeeklySummaryOut,
)
from app.services.finance_service import (
    WEEKLY_DEFAULT_DAYS,
    compute_daily_summary,
    compute_weekly_summary,
)
from app.services.manual_entry import validate_expense_amount

router = APIRouter(prefix="/finance", tags=["finance"])


@router.post("/expenses", response_model=ExpenseOut, status_code=201)
def create_expense(
    user_id: uuid.UUID, payload: ExpenseCreate, db: Session = Depends(get_db)
) -> Expense:
    """Log a manual cost (wash / fine / other). It lands in the day's
    finance summary immediately — every category reduces net income."""
    try:
        validate_expense_amount(payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    expense = Expense(
        user_id=user_id,
        category=payload.category,
        amount=payload.amount,
        expense_date=payload.expense_date or date.today(),
        note=payload.note,
    )
    db.add(expense)
    db.commit()
    db.refresh(expense)
    return expense


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
