"""Current surge coefficient per district — a five-source cascade,
best source wins per district:

1. Radar path: real kef readings OCR'd off the "Радар кэфа" app
   (kef_observations rows with a resolved district). Trust-filtered for OCR
   noise and aggregated by median within a 45-minute freshness window.
2. Stale-radar path: same readings aged 45–180 minutes. A 2-hour-old real kef
   still describes the district better than a synthetic number.
3. Near-radar path: districts with no own reading (off the scraper's screen or
   an OCR miss) take the median of their nearest radar-covered neighbours —
   surge is spatially smooth at district scale.
4. Live path: the latest fresh price_observations row per district, divided by
   that district's rolling baseline — the 15th percentile of prices over the
   last 7 days for the same reference route. The low percentile approximates
   the no-surge price without requiring the district to ever be fully quiet;
   the coefficient is clamped to >= 1.0.
5. Synthetic fallback: the latest demand_snapshots.surge_multiplier per
   district, which the worker's 5-minute tick keeps fresh. Only reached when
   the radar has produced nothing for 3 hours (scraper/emulator down).

The response marks each row's source so the UI can say honestly whether the
number is real.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.demand import DemandSnapshot
from app.models.district import District
from app.models.kef_observation import KefObservation
from app.models.pricing import PriceObservation

# A radar sweep runs every 30 minutes; the window covers one sweep plus its
# duration and some slack. Deliberately wider than the synthetic 30-minute
# window: a 40-minute-old real reading still beats a fresh synthetic one.
RADAR_FRESH_MINUTES = 45
# Readings older than fresh but younger than this still beat synthetic.
RADAR_STALE_MINUTES = 180
# Spatial fill: median over this many nearest radar-covered districts.
RADAR_NEAR_NEIGHBORS = 5
# ...but only when there is a meaningful covered set to borrow from.
RADAR_NEAR_MIN_COVERED = 10
# Yandex kef realistically tops out around 3–4; anything above this is an OCR
# misread (e.g. "18" for "1.8") that the ingest schema's loose bound let through.
RADAR_KEF_MAX_PLAUSIBLE = 6.0

# A live quote older than this no longer describes "now".
LIVE_FRESH_MINUTES = 90
BASELINE_DAYS = 7
BASELINE_PERCENTILE = 0.15
# Below this many observations the percentile is noise — use the minimum.
BASELINE_MIN_SAMPLES = 10


def get_current_surge(db: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = _radar_surge(db, now)
    covered = {r["district_id"] for r in rows}
    rows.extend(_radar_stale_surge(db, now, exclude=covered))
    rows.extend(_radar_near_surge(db, rows))
    covered = {r["district_id"] for r in rows}
    rows.extend(_live_surge(db, now, exclude=covered))
    covered = {r["district_id"] for r in rows}
    rows.extend(_synthetic_surge(db, now, exclude=covered))
    rows.sort(key=lambda r: r["district_id"])
    return rows


def radar_reading_value(kef_min: float, kef_max: float) -> float | None:
    """One trusted number out of a radar bubble's min–max range, or None if
    the reading looks like OCR garbage. The midpoint is the honest single
    value for a range shown across tariffs; clamped to >= 1.0 because a kef
    below 1 doesn't exist."""
    lo, hi = float(kef_min), float(kef_max)
    if lo > hi:
        lo, hi = hi, lo
    if lo <= 0 or hi > RADAR_KEF_MAX_PLAUSIBLE:
        return None
    return max(1.0, (lo + hi) / 2)


def aggregate_kef(values: list[float]) -> float | None:
    """Median of a district's in-window readings — robust to a single OCR
    outlier when a scraper sweep overlaps a driver's bot screenshot."""
    if not values:
        return None
    return round(median(values), 2)


def _radar_window(
    db: Session,
    since: datetime,
    until: datetime,
    source: str,
    exclude: set[int] = frozenset(),
) -> list[dict]:
    rows = db.execute(
        select(
            KefObservation.district_id,
            KefObservation.kef_min,
            KefObservation.kef_max,
            KefObservation.observed_at,
        ).where(
            KefObservation.observed_at >= since,
            KefObservation.observed_at < until,
            KefObservation.district_id.is_not(None),
        )
    ).all()

    by_district: dict[int, dict] = {}
    for district_id, kef_min, kef_max, observed_at in rows:
        if district_id in exclude:
            continue
        value = radar_reading_value(kef_min, kef_max)
        if value is None:
            continue
        group = by_district.setdefault(district_id, {"values": [], "observed_at": observed_at})
        group["values"].append(value)
        if observed_at > group["observed_at"]:
            group["observed_at"] = observed_at

    out = []
    for district_id, group in by_district.items():
        surge = aggregate_kef(group["values"])
        if surge is None:
            continue
        out.append(
            {
                "district_id": district_id,
                "surge": surge,
                "observed_at": group["observed_at"],
                "source": source,
            }
        )
    return out


def _radar_surge(db: Session, now: datetime) -> list[dict]:
    return _radar_window(db, now - timedelta(minutes=RADAR_FRESH_MINUTES), now, "radar")


def _radar_stale_surge(db: Session, now: datetime, exclude: set[int]) -> list[dict]:
    return _radar_window(
        db,
        now - timedelta(minutes=RADAR_STALE_MINUTES),
        now - timedelta(minutes=RADAR_FRESH_MINUTES),
        "radar_stale",
        exclude=exclude,
    )


def nearest_surge_median(
    lat: float, lng: float, covered: list[tuple[float, float, float]], k: int = RADAR_NEAR_NEIGHBORS
) -> float | None:
    """Median surge of the k covered districts nearest to (lat, lng).
    `covered` is (centroid_lat, centroid_lng, surge). Equirectangular distance
    is plenty at city scale."""
    if not covered:
        return None
    ranked = sorted(
        covered, key=lambda c: (c[0] - lat) ** 2 + ((c[1] - lng) * 0.56) ** 2  # cos(55.7°)
    )
    return round(median(c[2] for c in ranked[:k]), 2)


def _radar_near_surge(db: Session, radar_rows: list[dict]) -> list[dict]:
    """Spatial fill for districts the radar didn't cover: median of the nearest
    radar-covered neighbours. Runs on the already-fetched radar tiers only —
    a district is never filled from live/synthetic values."""
    if len(radar_rows) < RADAR_NEAR_MIN_COVERED:
        return []
    centroids = {
        district_id: (float(lat), float(lng))
        for district_id, lat, lng in db.execute(
            select(District.id, District.centroid_lat, District.centroid_lng)
        ).all()
    }
    covered_ids = {r["district_id"] for r in radar_rows}
    covered = [
        (*centroids[r["district_id"]], r["surge"]) for r in radar_rows if r["district_id"] in centroids
    ]
    observed_at = max(r["observed_at"] for r in radar_rows)

    out = []
    for district_id, (lat, lng) in centroids.items():
        if district_id in covered_ids:
            continue
        surge = nearest_surge_median(lat, lng, covered)
        if surge is None:
            continue
        out.append(
            {
                "district_id": district_id,
                "surge": surge,
                "observed_at": observed_at,
                "source": "radar_near",
            }
        )
    return out


def _live_surge(db: Session, now: datetime, exclude: set[int] = frozenset()) -> list[dict]:
    fresh_after = now - timedelta(minutes=LIVE_FRESH_MINUTES)
    latest = (
        select(
            PriceObservation.district_id,
            PriceObservation.price,
            PriceObservation.observed_at,
            func.row_number()
            .over(
                partition_by=PriceObservation.district_id,
                order_by=PriceObservation.observed_at.desc(),
            )
            .label("rn"),
        )
        .where(PriceObservation.observed_at >= fresh_after)
        .subquery()
    )
    latest_rows = db.execute(
        select(latest.c.district_id, latest.c.price, latest.c.observed_at).where(latest.c.rn == 1)
    ).all()
    if not latest_rows:
        return []

    baseline_after = now - timedelta(days=BASELINE_DAYS)
    baselines = {
        district_id: (float(p15), int(n), float(pmin))
        for district_id, p15, n, pmin in db.execute(
            select(
                PriceObservation.district_id,
                func.percentile_cont(BASELINE_PERCENTILE).within_group(PriceObservation.price),
                func.count(PriceObservation.id),
                func.min(PriceObservation.price),
            )
            .where(PriceObservation.observed_at >= baseline_after)
            .group_by(PriceObservation.district_id)
        ).all()
    }

    out = []
    for district_id, price, observed_at in latest_rows:
        if district_id in exclude:
            continue
        base = baselines.get(district_id)
        if base is None:
            continue
        p15, n, pmin = base
        baseline = p15 if n >= BASELINE_MIN_SAMPLES else pmin
        if baseline <= 0:
            continue
        out.append(
            {
                "district_id": district_id,
                "surge": round(max(1.0, float(price) / baseline), 2),
                "observed_at": observed_at,
                "source": "live",
            }
        )
    return out


def _synthetic_surge(db: Session, now: datetime, exclude: set[int]) -> list[dict]:
    fresh_after = now - timedelta(minutes=30)
    latest = (
        select(
            DemandSnapshot.district_id,
            DemandSnapshot.surge_multiplier,
            DemandSnapshot.observed_at,
            func.row_number()
            .over(
                partition_by=DemandSnapshot.district_id,
                order_by=DemandSnapshot.observed_at.desc(),
            )
            .label("rn"),
        )
        .where(DemandSnapshot.observed_at >= fresh_after)
        .subquery()
    )
    rows = db.execute(
        select(latest.c.district_id, latest.c.surge_multiplier, latest.c.observed_at).where(
            latest.c.rn == 1
        )
    ).all()
    return [
        {
            "district_id": district_id,
            "surge": round(float(surge), 2),
            "observed_at": observed_at,
            "source": "synthetic",
        }
        for district_id, surge, observed_at in rows
        if district_id not in exclude
    ]


def reference_route(centroid_lat: float, centroid_lng: float) -> tuple[float, float]:
    """Destination for a district's reference ride: the centroid pulled 35%
    toward the city center. Deterministic per district, so the baseline and
    every later quote price the same route. Central districts, whose centroid
    nearly IS the center, get a fixed ~2.8km northward leg instead — a
    few-hundred-meter route would always quote the minimum fare and carry no
    surge signal."""
    center_lat, center_lng = 55.7558, 37.6173
    d_lat = (center_lat - centroid_lat) * 0.35
    d_lng = (center_lng - centroid_lng) * 0.35
    if abs(d_lat) + abs(d_lng) < 0.02:
        d_lat, d_lng = 0.025, 0.0
    return centroid_lat + d_lat, centroid_lng + d_lng
