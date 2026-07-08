"""Current surge coefficient per district.

Live path: the latest fresh price_observations row per district, divided by
that district's rolling baseline — the 15th percentile of prices over the last
7 days for the same reference route. The low percentile approximates the
no-surge price without requiring the district to ever be fully quiet; the
coefficient is clamped to >= 1.0.

Fallback path (no fresh live prices — e.g. mock mode without a Yandex key):
the latest demand_snapshots.surge_multiplier per district, which the worker's
5-minute tick keeps fresh. The response marks each row's source so the UI can
say honestly whether the number is real.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.demand import DemandSnapshot
from app.models.pricing import PriceObservation

# A live quote older than this no longer describes "now".
LIVE_FRESH_MINUTES = 90
BASELINE_DAYS = 7
BASELINE_PERCENTILE = 0.15
# Below this many observations the percentile is noise — use the minimum.
BASELINE_MIN_SAMPLES = 10


def get_current_surge(db: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    rows = _live_surge(db, now)
    covered = {r["district_id"] for r in rows}
    rows.extend(_synthetic_surge(db, now, exclude=covered))
    rows.sort(key=lambda r: r["district_id"])
    return rows


def _live_surge(db: Session, now: datetime) -> list[dict]:
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
