"""Pure decision logic for the proactive «рядом скачок спроса» alert — a push
that fires when a district NEAR the driver is surging RIGHT NOW, at a
driver-set threshold. Deliberately DB-free and clock-injected (mirroring
monitoring.py / the surge_service helpers) so the threshold / cooldown /
nearby-set decisions are unit-testable without a database or a live bot; the
notification_service does the I/O and calls in here for the verdict.

Honesty note on "nearby": Telegram only ever hands us a location when the
driver actively sends one (the /where flow) — there is no passive/continuous
GPS. So we do NOT track the car live. "Nearby" is anchored on the driver's
home district plus its geographic neighbours (nearest-N by centroid distance,
the same cheap equirectangular metric surge_service already uses for spatial
fill). If a last-known location is ever persisted later, this set can be
recomputed around that point instead — the pure helpers here take centroids as
input and don't care where the anchor came from.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta

# Default surge threshold for a brand-new driver (overridable per profile via
# the bot's /alert command). Matches the home-only PRESHIFT_ALERT threshold so
# the two features speak the same language.
DEFAULT_SURGE_THRESHOLD = 1.5
# Re-alert for the SAME (driver, district) no more often than this. Short
# enough that a genuine second spike later the same day still gets through
# (unlike the once/day PRESHIFT dedup), long enough not to spam on one spike
# that lingers across several poll ticks.
PROXIMITY_COOLDOWN = timedelta(minutes=45)
# Only ever alert on a REAL radar reading — never on a synthetic/live-priced
# number. Same discipline as notification_service._PRESHIFT_REAL_SOURCES.
PROXIMITY_REAL_SOURCES = frozenset({"radar", "radar_stale", "radar_near"})
# "Nearby" = home district + this many nearest neighbours by centroid distance.
NEARBY_NEIGHBORS = 4
# Plain string tag for the pending-notification payload's "type" field. NOT a
# DB enum value: proximity dedup lives in its own proximity_surge_alert_log
# table, so the notification_type Postgres enum is left untouched.
PROXIMITY_SURGE_TYPE = "proximity_surge"

WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# Equirectangular distance is plenty at city scale. 0.563 = cos(55.7°), the
# same latitude correction surge_service.nearest_surge_median uses for Moscow.
_LAT_CORRECTION = math.cos(math.radians(55.7))
_KM_PER_DEG = 111.0
# 8-point compass, clockwise from North, in Russian shorthand.
_COMPASS = ["С", "СВ", "В", "ЮВ", "Ю", "ЮЗ", "З", "СЗ"]


def _equirect_sq(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    d_lat = lat1 - lat2
    d_lng = (lng1 - lng2) * _LAT_CORRECTION
    return d_lat * d_lat + d_lng * d_lng


def nearby_district_ids(
    home_id: int, centroids: dict[int, tuple[float, float]], k: int = NEARBY_NEIGHBORS
) -> set[int]:
    """The driver's home district plus its k nearest neighbours by centroid
    distance. `centroids` is {district_id: (lat, lng)}. Returns an empty set if
    the home district has no known centroid (nothing to anchor on)."""
    if home_id not in centroids:
        return set()
    h_lat, h_lng = centroids[home_id]
    ranked = sorted(
        ((did, _equirect_sq(h_lat, h_lng, lat, lng)) for did, (lat, lng) in centroids.items() if did != home_id),
        key=lambda item: item[1],
    )
    result = {home_id}
    result.update(did for did, _ in ranked[:k])
    return result


def distance_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    return round(math.sqrt(_equirect_sq(lat1, lng1, lat2, lng2)) * _KM_PER_DEG, 1)


def direction_hint(from_lat: float, from_lng: float, to_lat: float, to_lng: float) -> str | None:
    """8-point compass shorthand (С/СВ/В/…) from one point toward another, or
    None if the two points are effectively the same spot."""
    d_lat = to_lat - from_lat
    d_lng = (to_lng - from_lng) * _LAT_CORRECTION
    if abs(d_lat) < 1e-9 and abs(d_lng) < 1e-9:
        return None
    # atan2(east, north): 0° = North, 90° = East, growing clockwise.
    angle = math.degrees(math.atan2(d_lng, d_lat)) % 360
    return _COMPASS[int((angle + 22.5) // 45) % 8]


def surge_alert_due(surge: float, source: str, threshold: float) -> bool:
    """True only for a REAL radar reading at or above the driver's threshold —
    a synthetic/live-priced number never triggers a push."""
    return source in PROXIMITY_REAL_SOURCES and float(surge) >= float(threshold)


def in_cooldown(
    last_sent_at: datetime | None, now: datetime, cooldown: timedelta = PROXIMITY_COOLDOWN
) -> bool:
    """True while the last alert for this (driver, district) is still inside the
    cooldown window. Never sent before → not in cooldown."""
    if last_sent_at is None:
        return False
    return (now - last_sent_at) < cooldown


def is_within_shift(work_schedule: dict, weekday: int, hour: int) -> bool:
    """Whether `hour` falls inside the driver's configured shift for `weekday`.

    - No schedule configured at all → no time gate (True): a driver who never
      set hours still wants nearby-spike pushes.
    - A schedule exists but this weekday is empty → an explicit day off (False).
    - Otherwise gate on the day's first range [start_hour, end_hour).

    Matches the UTC-hour convention of notification_service._schedule_hour.
    """
    if not work_schedule:
        return True
    ranges = work_schedule.get(WEEKDAY_KEYS[weekday]) or []
    if not ranges:
        return False
    start_str, end_str = ranges[0].split("-")
    return int(start_str.split(":")[0]) <= hour < int(end_str.split(":")[0])


def select_surge_alerts(
    nearby_ids: set[int],
    surge_by_district: dict[int, dict],
    threshold: float,
    last_sent_by_district: dict[int, datetime],
    now: datetime,
    cooldown: timedelta = PROXIMITY_COOLDOWN,
) -> list[int]:
    """Pure core: which nearby districts should push a proximity alert right now.

    A district qualifies when it is in the nearby set, has a current REAL surge
    reading at/above `threshold`, and is not within its per-district cooldown.
    `surge_by_district` maps district_id -> {"surge", "source", ...};
    `last_sent_by_district` maps district_id -> last alert timestamp. Returns
    district ids sorted for stable output.
    """
    due: list[int] = []
    for district_id in nearby_ids:
        row = surge_by_district.get(district_id)
        if row is None:
            continue
        if not surge_alert_due(row["surge"], row["source"], threshold):
            continue
        if in_cooldown(last_sent_by_district.get(district_id), now, cooldown):
            continue
        due.append(district_id)
    return sorted(due)
