"""Computes finance_summaries from trips + driver_profiles + expenses. Feeds
both the finance dashboard and the "why is income lower today" chat answers.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import ExpenseCategory
from app.models.finance import Expense, FinanceSummary
from app.models.trip import Trip
from app.models.user import DriverProfile

# Simple flat-rate heuristic for the Russian self-employed ("самозанятый") tax
# regime — clearly an estimate, not tax advice.
SELF_EMPLOYED_TAX_RATE = 0.04


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def compute_daily_summary(db: Session, user_id: uuid.UUID, target_date: date) -> FinanceSummary:
    day_start, day_end = _day_bounds(target_date)

    trips = (
        db.execute(
            select(Trip).where(
                Trip.user_id == user_id, Trip.start_time >= day_start, Trip.start_time < day_end
            )
        )
        .scalars()
        .all()
    )
    expenses = (
        db.execute(
            select(Expense).where(Expense.user_id == user_id, Expense.expense_date == target_date)
        )
        .scalars()
        .all()
    )
    profile = db.execute(
        select(DriverProfile).where(DriverProfile.user_id == user_id)
    ).scalar_one_or_none()

    gross_income = sum(float(t.price) for t in trips)
    total_distance_km = sum(float(t.distance_km) for t in trips)

    fuel_cost = 0.0
    rental_cost = 0.0
    if profile:
        fuel_cost = (
            total_distance_km
            * float(profile.fuel_consumption_l_per_100km)
            / 100
            * float(profile.fuel_price_per_liter)
        )
        if profile.rental_cost_per_day:
            rental_cost = float(profile.rental_cost_per_day)
        elif profile.rental_cost_per_week:
            rental_cost = float(profile.rental_cost_per_week) / 7

    wash_cost = sum(float(e.amount) for e in expenses if e.category == ExpenseCategory.WASH)
    fines_cost = sum(float(e.amount) for e in expenses if e.category == ExpenseCategory.FINE)

    tax_estimate = gross_income * SELF_EMPLOYED_TAX_RATE
    depreciation_estimate = 0.0  # no car purchase price captured at onboarding yet (MVP)

    net_income = (
        gross_income - fuel_cost - rental_cost - wash_cost - fines_cost - tax_estimate - depreciation_estimate
    )

    online_hours = 0.0
    if trips:
        first_start = min(t.start_time for t in trips)
        last_end = max(t.end_time for t in trips)
        online_hours = max((last_end - first_start).total_seconds() / 3600, 0.01)

    income_per_hour = net_income / online_hours if online_hours > 0 else 0.0
    income_per_km = net_income / total_distance_km if total_distance_km > 0 else 0.0

    existing = db.execute(
        select(FinanceSummary).where(
            FinanceSummary.user_id == user_id, FinanceSummary.summary_date == target_date
        )
    ).scalar_one_or_none()

    values = dict(
        gross_income=round(gross_income, 2),
        net_income=round(net_income, 2),
        fuel_cost=round(fuel_cost, 2),
        rental_cost=round(rental_cost, 2),
        wash_cost=round(wash_cost, 2),
        fines_cost=round(fines_cost, 2),
        tax_estimate=round(tax_estimate, 2),
        depreciation_estimate=round(depreciation_estimate, 2),
        trips_count=len(trips),
        online_hours=round(online_hours, 2),
        income_per_hour=round(income_per_hour, 2),
        income_per_km=round(income_per_km, 2),
    )

    if existing:
        for k, v in values.items():
            setattr(existing, k, v)
        summary = existing
    else:
        summary = FinanceSummary(user_id=user_id, summary_date=target_date, **values)
        db.add(summary)

    db.commit()
    db.refresh(summary)
    return summary
