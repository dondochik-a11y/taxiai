"""Daily sync of real upcoming flights via AviationStack (live mode only).
Deliberately daily, not every 5-min tick: the free tier is only ~100
requests/month, so 3 calls/day (one per airport) stays safely under budget.
Mock mode is a no-op — the live-feed tick already lays down synthetic flights
every 5 minutes (see scripts/simulate_live_feed.py::_maybe_insert_flight).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401  (must import before any single app.models.* submodule)
from app.core.config import get_settings
from app.models.airport import AirportFlight
from app.providers.factory import get_flights_provider

AIRPORT_CODES = ["SVO", "VKO", "DME"]


def _parse_iso(value: str | None) -> datetime | None:
    # AviationStack returns ISO-8601 strings (e.g. "2026-07-08T11:20:00+00:00"),
    # not datetime objects — a DateTime(timezone=True) column needs a real
    # datetime, not a bare string, or the insert fails at the DBAPI level.
    if not value:
        return None
    return datetime.fromisoformat(value)


def sync_flights(session: Session) -> int:
    settings = get_settings()
    if settings.resolved_mode(settings.flights_provider_mode, settings.aviationstack_api_key) != "live":
        return 0

    provider = get_flights_provider(session)
    now = datetime.now(timezone.utc)
    inserted = 0
    for code in AIRPORT_CODES:
        for flight in provider.get_upcoming_flights(code, now):
            scheduled_time = _parse_iso(flight.get("scheduled_time"))
            if not scheduled_time:
                continue
            exists = session.execute(
                select(AirportFlight).where(
                    AirportFlight.airport_code == code,
                    AirportFlight.scheduled_time == scheduled_time,
                    AirportFlight.direction == flight.get("direction", "arrival"),
                )
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(
                AirportFlight(
                    airport_code=code,
                    scheduled_time=scheduled_time,
                    actual_time=_parse_iso(flight.get("actual_time")),
                    direction=flight.get("direction", "arrival"),
                    status=flight.get("status") or "on_time",
                    delay_minutes=flight.get("delay_minutes"),
                    source="live",
                )
            )
            inserted += 1
    session.commit()
    return inserted


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        n = sync_flights(db)
        print(f"Synced {n} new flight rows.")
    finally:
        db.close()
