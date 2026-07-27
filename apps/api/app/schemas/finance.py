from datetime import date

from pydantic import BaseModel, ConfigDict


class FinanceSummaryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    summary_date: date
    gross_income: float
    net_income: float
    fuel_cost: float
    rental_cost: float
    wash_cost: float
    fines_cost: float
    tax_estimate: float
    depreciation_estimate: float
    trips_count: int
    online_hours: float
    income_per_hour: float
    income_per_km: float

    # Per-driver daily-goal progress (see finance_service.goal_progress). All
    # None when the driver has no goal set; not persisted on finance_summaries.
    daily_goal: float | None = None
    goal_remaining: float | None = None
    goal_reached: bool = False
    goal_pct: float | None = None


class WeeklyTotalsOut(BaseModel):
    gross_income: float
    net_income: float
    trips_count: int
    online_hours: float
    income_per_hour: float
    income_per_km: float


class WeeklySummaryOut(BaseModel):
    """One response covering N days (default 14) of daily figures + totals, so
    the finance dashboard makes a single call instead of N per-day calls."""

    days: list[FinanceSummaryOut]
    totals: WeeklyTotalsOut
