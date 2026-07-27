"""Pure logic behind office task #100 Phase 2 — shift-hours calc, goal progress
and weekly totals. DB-free and clock-injected, mirroring test_alerts.py: the
DB-bound bits (toggle, per-day upsert) lean on Postgres, so the logic worth
testing is the standalone helpers."""
from datetime import datetime, timedelta, timezone

from app.services.finance_service import goal_progress, weekly_totals
from app.services.shift_service import (
    elapsed_hours,
    merge_intervals,
    shift_hours_for_day,
)

DAY_START = datetime(2026, 7, 27, 0, 0, tzinfo=timezone.utc)
DAY_END = DAY_START + timedelta(days=1)
NOON = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 27, hour, minute, tzinfo=timezone.utc)


class TestShiftHoursForDay:
    def test_single_closed_shift(self):
        shifts = [(_at(8), _at(14))]
        assert shift_hours_for_day(shifts, DAY_START, DAY_END, NOON) == 6.0

    def test_open_shift_runs_until_now(self):
        # Started 10:00, no end, now is 12:00 → 2 online hours so far.
        shifts = [(_at(10), None)]
        assert shift_hours_for_day(shifts, DAY_START, DAY_END, NOON) == 2.0

    def test_no_shift_returns_none_for_fallback(self):
        # No shift on the day → None, so finance falls back to trip-span inference.
        assert shift_hours_for_day([], DAY_START, DAY_END, NOON) is None

    def test_break_between_shifts_not_counted(self):
        # 08–12 and 14–18 = 8 real hours; the 2h lunch break is NOT online.
        shifts = [(_at(8), _at(12)), (_at(14), _at(18))]
        assert shift_hours_for_day(shifts, DAY_START, DAY_END, NOON) == 8.0

    def test_overlapping_shifts_unioned_not_summed(self):
        # 08–12 and 10–14 overlap → union is 08–14 = 6h, not 4+4=8.
        shifts = [(_at(8), _at(12)), (_at(10), _at(14))]
        assert shift_hours_for_day(shifts, DAY_START, DAY_END, NOON) == 6.0

    def test_shift_clipped_to_day_window(self):
        # Started yesterday 22:00, ended today 03:00 → only the 3h inside today.
        shifts = [(DAY_START - timedelta(hours=2), _at(3))]
        assert shift_hours_for_day(shifts, DAY_START, DAY_END, NOON) == 3.0

    def test_shift_entirely_outside_day_ignored(self):
        prev_start = DAY_START - timedelta(hours=5)
        prev_end = DAY_START - timedelta(hours=1)
        assert shift_hours_for_day([(prev_start, prev_end)], DAY_START, DAY_END, NOON) is None


class TestMergeIntervals:
    def test_empty(self):
        assert merge_intervals([]) == []

    def test_disjoint_preserved(self):
        ivs = [(_at(8), _at(9)), (_at(11), _at(12))]
        assert merge_intervals(ivs) == ivs

    def test_touching_merged(self):
        assert merge_intervals([(_at(8), _at(10)), (_at(10), _at(12))]) == [(_at(8), _at(12))]


class TestElapsedHours:
    def test_basic(self):
        assert elapsed_hours(_at(9), _at(14, 30)) == 5.5

    def test_never_negative(self):
        assert elapsed_hours(_at(14), _at(9)) == 0.0


class TestGoalProgress:
    def test_no_goal_is_all_none(self):
        assert goal_progress(3000.0, None) == {
            "daily_goal": None,
            "goal_remaining": None,
            "goal_reached": False,
            "goal_pct": None,
        }

    def test_zero_goal_treated_as_no_goal(self):
        assert goal_progress(3000.0, 0.0)["daily_goal"] is None

    def test_partial_progress(self):
        r = goal_progress(3000.0, 5000.0)
        assert r["daily_goal"] == 5000.0
        assert r["goal_remaining"] == 2000.0
        assert r["goal_reached"] is False
        assert r["goal_pct"] == 60.0

    def test_exactly_reached(self):
        r = goal_progress(5000.0, 5000.0)
        assert r["goal_reached"] is True
        assert r["goal_remaining"] == 0.0
        assert r["goal_pct"] == 100.0

    def test_over_goal_caps_pct_and_zero_remaining(self):
        r = goal_progress(6000.0, 5000.0)
        assert r["goal_reached"] is True
        assert r["goal_remaining"] == 0.0
        assert r["goal_pct"] == 100.0


class TestWeeklyTotals:
    def _day(self, gross, net, trips, hours, ipk):
        return {
            "gross_income": gross,
            "net_income": net,
            "trips_count": trips,
            "online_hours": hours,
            "income_per_km": ipk,
        }

    def test_sums_and_derived_rates(self):
        days = [
            self._day(1500, 1000, 10, 5.0, 40.0),  # distance = 1000/40 = 25 km
            self._day(800, 500, 6, 5.0, 25.0),  # distance = 500/25 = 20 km
        ]
        totals = weekly_totals(days)
        assert totals["gross_income"] == 2300.0
        assert totals["net_income"] == 1500.0
        assert totals["trips_count"] == 16
        assert totals["online_hours"] == 10.0
        assert totals["income_per_hour"] == 150.0  # 1500 net / 10 h
        # distance total 45 km → 1500 / 45 = 33.33 ₽/km
        assert totals["income_per_km"] == 33.33

    def test_zero_hours_and_no_distance_stay_zero(self):
        days = [self._day(0, 0, 0, 0.0, 0.0)]
        totals = weekly_totals(days)
        assert totals["income_per_hour"] == 0.0
        assert totals["income_per_km"] == 0.0
        assert totals["trips_count"] == 0
