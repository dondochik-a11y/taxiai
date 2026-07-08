"""One-off backfill: populates ~90 days of internally-consistent synthetic
history (weather, traffic, calendar events, airport flights, metro incidents,
demand snapshots, and a demo driver's trips) so the dashboard, forecasting
pipeline, and pattern-mining are all demoable end-to-end with zero external
API keys and no real historical dataset.

Usage:
    python scripts/seed_synthetic_history.py [--force]

--force deletes existing synthetic rows in the backfill window first (idempotent
reseed). Without it, the script refuses to run if demand_snapshots already has
synthetic rows, to avoid silently duplicating history.
"""
from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import delete, insert, select  # noqa: E402

from app.db.base import Base  # noqa: E402,F401  (must import before any single app.models.* submodule)
from app.db.session import SessionLocal  # noqa: E402
from app.models.airport import AirportFlight  # noqa: E402
from app.models.calendar import CalendarEvent  # noqa: E402
from app.models.demand import DemandSnapshot  # noqa: E402
from app.models.district import District  # noqa: E402
from app.models.metro import MetroIncident  # noqa: E402
from app.models.traffic import TrafficObservation  # noqa: E402
from app.models.trip import Trip  # noqa: E402
from app.models.user import DriverProfile, User  # noqa: E402
from app.models.weather import WeatherObservation  # noqa: E402
from app.synth import generator as gen  # noqa: E402
from app.synth import signal_config as cfg  # noqa: E402

CHUNK_SIZE = 5000
DEMO_USER_EMAIL = "demo@taxiai.local"


def _bulk_insert(session, model, rows: list[dict]) -> None:
    if not rows:
        return
    for i in range(0, len(rows), CHUNK_SIZE):
        session.execute(insert(model), rows[i : i + CHUNK_SIZE])


def _load_districts(session) -> list[gen.DistrictInfo]:
    districts = session.execute(select(District)).scalars().all()
    if not districts:
        raise RuntimeError(
            "No districts found. Run `alembic upgrade head` first (migration 0002 seeds them)."
        )
    return [
        gen.DistrictInfo(d.id, d.name, float(d.centroid_lat), float(d.centroid_lng), d.airport_nearby)
        for d in districts
    ]


def _get_or_create_demo_user(session) -> uuid.UUID:
    user = session.execute(select(User).where(User.email == DEMO_USER_EMAIL)).scalar_one_or_none()
    if user:
        return user.id
    user = User(email=DEMO_USER_EMAIL, city="Moscow")
    session.add(user)
    session.flush()
    profile = DriverProfile(
        user_id=user.id,
        car_make="Hyundai",
        car_model="Solaris",
        car_year=2021,
        tariff_plan="economy",
        fuel_type="petrol95",
        fuel_consumption_l_per_100km=7.5,
        fuel_price_per_liter=58.0,
        rental_cost_per_day=2500.0,
        work_schedule={"mon": ["08:00-20:00"], "tue": ["08:00-20:00"], "wed": ["08:00-20:00"]},
    )
    session.add(profile)
    session.flush()
    return user.id


def _clear_existing_synthetic(session) -> None:
    for model in (DemandSnapshot, Trip, TrafficObservation, WeatherObservation, AirportFlight, MetroIncident, CalendarEvent):
        session.execute(delete(model).where(model.source == "synthetic"))


def main(force: bool = False) -> None:
    session = SessionLocal()
    try:
        existing = session.execute(select(DemandSnapshot.id).limit(1)).first()
        if existing and not force:
            print("demand_snapshots already has rows. Re-run with --force to reseed.")
            return
        if existing and force:
            print("Clearing existing synthetic rows...")
            _clear_existing_synthetic(session)
            session.commit()

        districts = _load_districts(session)
        district_by_id = {d.id: d for d in districts}
        user_id = _get_or_create_demo_user(session)
        session.commit()

        # Hour-floored, not 5-min-floored: weather/traffic are generated hourly (see
        # below), and app/ml/features.py joins demand rows to them via an hour-floor
        # key. Anchoring "now" to a non-zero minute here would silently desync that
        # join for the entire backfill (weather rows would never match any demand
        # row's hour-floor) — caught by inspecting real seeded data, not by the
        # earlier dry-run checks. The live feed tick (simulate_live_feed.py) already
        # floors correctly and fills in the remaining partial hour once it runs.
        now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
        start = now - timedelta(days=cfg.BACKFILL_DAYS)
        high_res_start = now - timedelta(days=cfg.HIGH_RES_RECENT_DAYS)

        print(f"Backfilling {cfg.BACKFILL_DAYS} days from {start} to {now} "
              f"(5-min resolution from {high_res_start})...")

        print("Generating calendar events...")
        calendar_rows = gen.generate_calendar_events(start.date(), now.date(), districts)
        _bulk_insert(session, CalendarEvent, calendar_rows)
        session.commit()

        print("Generating airport flights...")
        flight_rows = gen.generate_airport_flights(start, now)
        _bulk_insert(session, AirportFlight, flight_rows)
        session.commit()

        print("Generating metro incidents...")
        metro_rows = gen.generate_metro_incidents(start, now)
        _bulk_insert(session, MetroIncident, metro_rows)
        session.commit()

        print("Generating weather (hourly random walk)...")
        weather_state = gen.WeatherState(temperature_c=gen.seasonal_baseline_temp(start.date()))
        weather_rows: list[dict] = []
        weather_by_hour: dict[datetime, dict] = {}
        t = start
        while t < now:
            weather_state, row = gen.step_weather(weather_state, t)
            weather_rows.append(row)
            weather_by_hour[t] = row
            t += timedelta(hours=1)
        _bulk_insert(session, WeatherObservation, weather_rows)
        session.commit()

        print("Generating traffic (hourly, per district)...")
        hours = list(weather_by_hour.keys())
        traffic_rows = gen.generate_traffic(hours, districts)
        _bulk_insert(session, TrafficObservation, traffic_rows)
        session.commit()

        ctx = gen.build_context(districts, calendar_rows, flight_rows, district_by_id)

        print("Generating demand snapshots (this is the core signal-bearing table)...")
        demand_rows: list[dict] = []
        demand_by_district_hour_per_day: dict[tuple, dict] = {}

        def _slot_times_for_hour(hour_dt: datetime, high_res: bool) -> list[datetime]:
            if not high_res:
                return [hour_dt]
            return [hour_dt + timedelta(minutes=5 * i) for i in range(12)]

        for hour_dt in hours:
            high_res = hour_dt >= high_res_start
            weather_row = weather_by_hour.get(hour_dt)
            for slot_dt in _slot_times_for_hour(hour_dt, high_res):
                for d in districts:
                    level, surge = gen.demand_for_slot(ctx, d, slot_dt, weather_row)
                    demand_rows.append(
                        {
                            "district_id": d.id,
                            "observed_at": slot_dt,
                            "demand_level": level,
                            "surge_multiplier": surge,
                            "active_orders_estimate": int(level * 40),
                            "free_drivers_estimate": int((1 - level) * 25) + 3,
                            "source": "synthetic",
                        }
                    )
                    day_key = hour_dt.date()
                    demand_by_district_hour_per_day.setdefault(day_key, {})
                    prev = demand_by_district_hour_per_day[day_key].get((d.id, hour_dt.hour))
                    demand_by_district_hour_per_day[day_key][(d.id, hour_dt.hour)] = (
                        level if prev is None else (prev + level) / 2
                    )
            if len(demand_rows) >= CHUNK_SIZE:
                _bulk_insert(session, DemandSnapshot, demand_rows)
                session.commit()
                demand_rows = []
        _bulk_insert(session, DemandSnapshot, demand_rows)
        session.commit()

        print("Generating trips for the demo driver...")
        trip_rows: list[dict] = []
        d = start.date()
        import random

        day_rng = random.Random(cfg.RANDOM_SEED + 1)
        while d < now.date():
            demand_map = demand_by_district_hour_per_day.get(d, {})
            if demand_map:
                trips_target = day_rng.randint(12, 22)
                trip_rows.extend(
                    gen.generate_trips_for_day(
                        ctx, d, districts, demand_map, weather_by_hour, user_id, trips_target
                    )
                )
            d += timedelta(days=1)
        for row in trip_rows:
            row["id"] = uuid.uuid4()
        _bulk_insert(session, Trip, trip_rows)
        session.commit()

        print(
            f"Done. Seeded {len(weather_rows)} weather rows, {len(traffic_rows)} traffic rows, "
            f"{len(flight_rows)} flight rows, {len(metro_rows)} metro rows, "
            f"{len(calendar_rows)} calendar rows, {len(trip_rows)} trips."
        )
    finally:
        session.close()


if __name__ == "__main__":
    main(force="--force" in sys.argv)
