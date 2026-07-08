"""Real-time arrival detection via OpenSky (live mode only). Inserts one
airport_flights row per aircraft currently detected landing/landed near each
airport — feeding app/synth/generator.py's arrival-density demand signal with
genuine real-time data, on a much shorter interval than AviationStack's daily
schedule sync (see app/jobs/ingest_flights.py) can afford.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401  (must import before any single app.models.* submodule)
from app.core.config import get_settings
from app.models.airport import AirportFlight
from app.models.district import District
from app.synth.signal_config import AIRPORT_DISTRICTS

_DISTRICT_NAME_TO_CODE = dict(zip(AIRPORT_DISTRICTS, ["SVO", "VKO", "DME"], strict=True))


def sync_realtime_arrivals(session: Session) -> int:
    settings = get_settings()
    required_key = settings.opensky_client_id and settings.opensky_client_secret
    if settings.resolved_mode(settings.opensky_provider_mode, required_key) != "live":
        return 0

    from app.providers.live.flights_opensky import OpenSkyArrivalDetector

    detector = OpenSkyArrivalDetector()
    districts = session.execute(
        select(District).where(District.name.in_(AIRPORT_DISTRICTS))
    ).scalars().all()

    now = datetime.now(timezone.utc)
    inserted = 0
    for d in districts:
        code = _DISTRICT_NAME_TO_CODE.get(d.name)
        if not code:
            continue
        count = detector.count_arrivals_near(float(d.centroid_lat), float(d.centroid_lng))
        for _ in range(count):
            session.add(
                AirportFlight(
                    airport_code=code,
                    scheduled_time=now,
                    actual_time=now,
                    direction="arrival",
                    status="landed",
                    delay_minutes=None,
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
        n = sync_realtime_arrivals(db)
        print(f"Detected {n} real-time arrivals near Moscow airports.")
    finally:
        db.close()
