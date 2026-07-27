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
from app.services.shift_service import get_shifts_overlapping_day, shift_hours_for_day

# Simple flat-rate heuristic for the Russian self-employed ("самозанятый") tax
# regime — clearly an estimate, not tax advice.
SELF_EMPLOYED_TAX_RATE = 0.04


def _day_bounds(d: date) -> tuple[datetime, datetime]:
    start = datetime.combine(d, time.min, tzinfo=timezone.utc)
    return start, start + timedelta(days=1)


def goal_progress(net_income: float, goal: float | None) -> dict:
    """Pure progress-toward-daily-goal calc, surfaced as API fields and rendered
    by the bot. `goal` is the driver's daily net-income target (None = no goal).
    Returns the goal echo, how much is still needed, whether it's reached, and a
    0–100 percentage — DB-free so it can be unit-tested directly."""
    if not goal or goal <= 0:
        return {"daily_goal": None, "goal_remaining": None, "goal_reached": False, "goal_pct": None}
    remaining = max(goal - net_income, 0.0)
    reached = net_income >= goal
    pct = min(net_income / goal * 100, 100.0) if net_income > 0 else 0.0
    return {
        "daily_goal": round(float(goal), 2),
        "goal_remaining": round(remaining, 2),
        "goal_reached": reached,
        "goal_pct": round(pct, 1),
    }


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

    # Online hours: prefer real shift boundaries when the driver logged a shift
    # for this day (honest ₽/hour that doesn't count breaks as online); fall
    # back to the old first-trip→last-trip span when no shift exists.
    trip_hours = 0.0
    if trips:
        first_start = min(t.start_time for t in trips)
        last_end = max(t.end_time for t in trips)
        trip_hours = max((last_end - first_start).total_seconds() / 3600, 0.01)

    now = datetime.now(timezone.utc)
    shifts = get_shifts_overlapping_day(db, user_id, day_start, day_end)
    shift_hours = shift_hours_for_day(
        [(s.started_at, s.ended_at) for s in shifts], day_start, day_end, now
    )
    online_hours = shift_hours if shift_hours is not None else trip_hours

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

    # Goal progress is per-driver, not persisted per summary row — attach it as
    # transient attributes so FinanceSummaryOut (from_attributes) can surface it
    # without a schema/table coupling. Set after refresh so it survives.
    goal = float(profile.daily_goal_income) if profile and profile.daily_goal_income else None
    for key, value in goal_progress(float(summary.net_income), goal).items():
        setattr(summary, key, value)
    return summary


WEEKLY_DEFAULT_DAYS = 14


def weekly_totals(days: list[dict]) -> dict:
    """Aggregate a list of per-day summary dicts into week totals. ₽/hour is
    net over total online hours; ₽/km recovers each day's distance from its
    stored net÷(₽/km) (exact, since ₽/km == net/distance) so the week rate isn't
    a naive average of ratios. DB-free for direct unit testing."""
    gross = sum(d["gross_income"] for d in days)
    net = sum(d["net_income"] for d in days)
    trips = sum(d["trips_count"] for d in days)
    hours = sum(d["online_hours"] for d in days)
    distance = sum(d["net_income"] / d["income_per_km"] for d in days if d["income_per_km"])
    return {
        "gross_income": round(gross, 2),
        "net_income": round(net, 2),
        "trips_count": trips,
        "online_hours": round(hours, 2),
        "income_per_hour": round(net / hours, 2) if hours > 0 else 0.0,
        "income_per_km": round(net / distance, 2) if distance > 0 else 0.0,
    }


def compute_weekly_summary(
    db: Session, user_id: uuid.UUID, end_date: date, days: int = WEEKLY_DEFAULT_DAYS
) -> dict:
    """N days (default 14) of daily figures ending on `end_date` (inclusive),
    oldest→newest, plus totals — in one pass. Reuses compute_daily_summary per
    day (same upsert the /daily-summary endpoint does), replacing the web's
    N separate calls."""
    day_summaries = [
        compute_daily_summary(db, user_id, end_date - timedelta(days=offset))
        for offset in range(days - 1, -1, -1)
    ]
    totals = weekly_totals(
        [
            {
                "gross_income": float(s.gross_income),
                "net_income": float(s.net_income),
                "trips_count": int(s.trips_count),
                "online_hours": float(s.online_hours),
                "income_per_km": float(s.income_per_km),
            }
            for s in day_summaries
        ]
    )
    return {"days": day_summaries, "totals": totals}
