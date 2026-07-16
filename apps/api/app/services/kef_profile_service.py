"""Hour-of-week kef profiles from accumulated radar observations.

The radar scraper stores real per-district kefs every 30 minutes
(kef_observations, 90-day retention). Aggregating them by
(district, weekday, hour) gives an empirical "what is the kef usually like
here at this time" profile — the approximate real-data forecast the ML model
can't provide yet (it is still trained on synthetic demand history).

Lookup falls back gracefully while history accumulates:
(district, weekday, hour) → (district, hour, any weekday) → (city, weekday,
hour) → None. Hours are Moscow local (kef patterns follow local rush hours);
Moscow has no DST, so a fixed UTC+3 conversion is exact.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from statistics import median

from sqlalchemy import Integer, extract, func, select
from sqlalchemy.orm import Session

from app.models.kef_observation import KefObservation
from app.services.surge_service import RADAR_KEF_MAX_PLAUSIBLE

PROFILE_DAYS = 90
# Below this many readings a (district, weekday, hour) cell is noise — fall
# through to the wider aggregates instead.
MIN_CELL_SAMPLES = 3

MSK_OFFSET = timedelta(hours=3)


def load_kef_profiles(db: Session) -> dict:
    """One grouped query over the kef history, then in-memory rollups.

    Returns {"exact": {(district_id, weekday, hour): (median, n)},
             "district_hour": {(district_id, hour): median},
             "city_hour": {(weekday, hour): median}}.
    Weekday is Python's convention (0 = Monday).
    """
    local_ts = KefObservation.observed_at + MSK_OFFSET
    # PostgreSQL: isodow 1..7 (Mon..Sun) -> 0..6; midpoint of the bubble's range.
    value = (KefObservation.kef_min + KefObservation.kef_max) / 2.0
    rows = db.execute(
        select(
            KefObservation.district_id,
            (extract("isodow", local_ts) - 1).cast(Integer).label("weekday"),
            extract("hour", local_ts).cast(Integer).label("hour"),
            func.percentile_cont(0.5).within_group(value),
            func.count(KefObservation.id),
        )
        .where(
            KefObservation.observed_at >= func.now() - timedelta(days=PROFILE_DAYS),
            KefObservation.district_id.is_not(None),
            KefObservation.kef_min > 0,
            KefObservation.kef_max <= RADAR_KEF_MAX_PLAUSIBLE,
        )
        .group_by(KefObservation.district_id, "weekday", "hour")
    ).all()

    exact: dict[tuple[int, int, int], tuple[float, int]] = {}
    by_district_hour: dict[tuple[int, int], list[float]] = defaultdict(list)
    by_city_hour: dict[tuple[int, int], list[float]] = defaultdict(list)
    for district_id, weekday, hour, med, n in rows:
        med = max(1.0, float(med))
        exact[(district_id, weekday, hour)] = (med, int(n))
        by_district_hour[(district_id, hour)].append(med)
        by_city_hour[(weekday, hour)].append(med)

    return {
        "exact": exact,
        "district_hour": {k: round(median(v), 2) for k, v in by_district_hour.items()},
        "city_hour": {k: round(median(v), 2) for k, v in by_city_hour.items()},
    }


def profile_kef(profiles: dict, district_id: int, target_time_utc: datetime) -> float | None:
    """Expected kef for a district at a UTC moment, or None if the history has
    nothing useful yet."""
    local = target_time_utc + MSK_OFFSET
    weekday, hour = local.weekday(), local.hour

    cell = profiles["exact"].get((district_id, weekday, hour))
    if cell is not None and cell[1] >= MIN_CELL_SAMPLES:
        return round(cell[0], 2)
    fallback = profiles["district_hour"].get((district_id, hour))
    if fallback is not None:
        return fallback
    return profiles["city_hour"].get((weekday, hour))
