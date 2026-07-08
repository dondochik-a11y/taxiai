"""The trained ML model only forecasts 15-120 minutes ahead (see
app/ml/inference.py) — not enough for a "best hours to work today" morning
plan. For that specific need we fall back to a simple historical average: mean
demand_level by hour of day, for the same weekday, across all accumulated
history (synthetic or, later, real). Deliberately simple and honestly labeled
as a historical average rather than a same-day forecast.
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

WINDOW_HOURS = 4
TOP_WINDOWS = 2

# Postgres EXTRACT(DOW ...) is 0=Sunday..6=Saturday; Python's date.weekday() is 0=Monday..6=Sunday.
_PYTHON_WEEKDAY_TO_PG_DOW = {0: 1, 1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 0}


def _hourly_demand_by_weekday(session: Session, python_weekday: int) -> dict[int, float]:
    pg_dow = _PYTHON_WEEKDAY_TO_PG_DOW[python_weekday]
    rows = session.execute(
        text(
            """
            SELECT EXTRACT(HOUR FROM observed_at)::int AS hour, AVG(demand_level) AS avg_demand
            FROM demand_snapshots
            WHERE EXTRACT(DOW FROM observed_at) = :dow
            GROUP BY hour
            """
        ),
        {"dow": pg_dow},
    ).all()
    return {int(r.hour): float(r.avg_demand) for r in rows}


def _best_windows(hourly: dict[int, float], window_hours: int, top_n: int) -> list[tuple[int, int]]:
    if not hourly:
        return []
    scores = []
    for start in range(0, 24 - window_hours + 1):
        window_hours_range = range(start, start + window_hours)
        if not all(h in hourly for h in window_hours_range):
            continue
        scores.append((sum(hourly[h] for h in window_hours_range), start))
    scores.sort(reverse=True)

    chosen: list[tuple[int, int]] = []
    used_hours: set[int] = set()
    for _score, start in scores:
        window = set(range(start, start + window_hours))
        if window & used_hours:
            continue
        chosen.append((start, start + window_hours))
        used_hours |= window
        if len(chosen) >= top_n:
            break
    return sorted(chosen)


def get_daily_plan(session: Session, python_weekday: int) -> list[dict]:
    """Returns up to TOP_WINDOWS non-overlapping best-hours windows, e.g.
    [{"start_hour": 7, "end_hour": 11}, {"start_hour": 18, "end_hour": 22}]."""
    hourly = _hourly_demand_by_weekday(session, python_weekday)
    windows = _best_windows(hourly, WINDOW_HOURS, TOP_WINDOWS)
    return [{"start_hour": s, "end_hour": e} for s, e in windows]
