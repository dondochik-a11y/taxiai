"""Pure observability logic shared by the worker watchdogs, the retrain job and
the operator /health surface. Deliberately DB-free and side-effect-free so the
threshold/throttle decisions are unit-testable without a database or a live
Telegram bot — the scheduler and API layers do the I/O and call in here for the
verdict.

Two silent failures motivated this module:
  * the weekly retrain was OOM-killed for ~2 weeks and kept serving a stale
    model with nothing visible  -> model-staleness decision below;
  * kef collection had multi-hour partial-coverage gaps for days, unnoticed
    (the old watchdog only caught a TOTAL blackout) -> radar coverage levels.
"""
from __future__ import annotations

from datetime import datetime, timedelta

# --- Model staleness -------------------------------------------------------
# Retrain is weekly (Mon 03:30 UTC). Allow a day of slack for a delayed/long
# run before we call it stale, so a healthy weekly cadence never false-alarms.
MODEL_STALE_AFTER = timedelta(days=8)
# While it stays stale, re-remind at this cadence instead of once-and-silent —
# a single day-8 alert is easy to miss over a multi-week outage.
STALE_ALERT_THROTTLE = timedelta(days=2)

# --- Radar (kef) coverage --------------------------------------------------
# ~130 districts are covered by two emulator halves every ~13 min, so a healthy
# hour yields well over 100 distinct districts.
RADAR_TOTAL_DISTRICTS = 130
# Below this the radar is effectively out (kept from the original watchdog).
RADAR_MIN_DISTRICTS = 10
# Between MIN and this floor the feed is only partially collecting — the exact
# multi-hour gap that went unnoticed. Alert on it too, not just a full blackout.
RADAR_COVERAGE_FLOOR = 60
# No kef row at all in this window = the scraper/bot pipeline is silent even if
# the last hour still shows stale-but-present coverage.
RADAR_SILENCE_MINUTES = 20
# While degraded/down, re-alert at most this often so a persistent problem
# doesn't spam Tim's notification bot every hourly tick.
RADAR_ALERT_THROTTLE = timedelta(hours=3)

_RADAR_SEVERITY = {"ok": 0, "degraded": 1, "down": 2}


def is_model_stale(
    trained_at: datetime | None, now: datetime, threshold: timedelta = MODEL_STALE_AFTER
) -> bool:
    """True when the latest retrain is missing or older than `threshold`.
    A missing trained_at (no model_metrics rows / no artifact) counts as stale —
    that is itself the "retrain never ran" signal."""
    if trained_at is None:
        return True
    return (now - trained_at) >= threshold


def should_alert_staleness(
    is_stale: bool,
    was_stale: bool,
    now: datetime,
    last_alert_at: datetime | None,
    throttle: timedelta = STALE_ALERT_THROTTLE,
) -> bool:
    """Emit on the fresh->stale edge, on recovery (stale->fresh), and while it
    stays stale no more often than `throttle`."""
    if is_stale and not was_stale:
        return True
    if not is_stale and was_stale:
        return True
    if is_stale and was_stale:
        return last_alert_at is None or (now - last_alert_at) >= throttle
    return False


def classify_radar_coverage(
    coverage_last_hour: int,
    rows_last_silence_window: int,
    *,
    min_districts: int = RADAR_MIN_DISTRICTS,
    coverage_floor: int = RADAR_COVERAGE_FLOOR,
) -> str:
    """Map raw counts to a health level: 'ok' | 'degraded' | 'down'.

    - down: no fresh rows at all in the silence window, or last-hour distinct
      districts below the total-outage floor;
    - degraded: rows are arriving but distinct-district coverage is below the
      partial-collection floor (the multi-hour-gap case);
    - ok: coverage at or above the floor.
    """
    if rows_last_silence_window <= 0 or coverage_last_hour < min_districts:
        return "down"
    if coverage_last_hour < coverage_floor:
        return "degraded"
    return "ok"


def should_alert_radar(
    level: str,
    prev_level: str,
    now: datetime,
    last_alert_at: datetime | None,
    throttle: timedelta = RADAR_ALERT_THROTTLE,
) -> bool:
    """Alert on any change into/within a bad state that worsens, on recovery to
    ok, and while stuck in a bad state no more often than `throttle`. Improving
    but still-bad (down->degraded) is throttled, not silent."""
    if level == prev_level:
        if level == "ok":
            return False
        return last_alert_at is None or (now - last_alert_at) >= throttle
    if level == "ok":
        return True  # recovery
    if prev_level == "ok":
        return True  # newly bad
    # both bad, level changed: alert immediately if it worsened, else throttle.
    if _RADAR_SEVERITY[level] > _RADAR_SEVERITY[prev_level]:
        return True
    return last_alert_at is None or (now - last_alert_at) >= throttle


def build_mae_by_horizon(per_horizon: dict[int, float | None]) -> dict[str, float]:
    """Normalize a {horizon_minutes: mae} mapping into the JSON-serializable,
    rounded shape stored in model_metrics.mae_by_horizon. Skips horizons with no
    holdout rows (None), and stringifies keys so JSONB round-trips cleanly."""
    return {
        str(h): round(float(v), 4)
        for h, v in per_horizon.items()
        if v is not None
    }
