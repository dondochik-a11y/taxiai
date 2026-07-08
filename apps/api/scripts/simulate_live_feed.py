"""Ongoing synthetic "live" feed: appends one new tick of data at the current
wall-clock time, exactly like a real ingestion job would. Meant to be called
every 5 minutes by the worker's scheduler (app/jobs/scheduler.py, M3) so
"today" always has fresh data flowing in without manual reseeding.

Can also be run standalone for a single tick:
    python scripts/simulate_live_feed.py
"""
from __future__ import annotations

import logging
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import insert, select  # noqa: E402

from app.db.base import Base  # noqa: E402,F401  (must import before any single app.models.* submodule)
from app.db.session import SessionLocal  # noqa: E402
from app.models.airport import AirportFlight  # noqa: E402
from app.models.calendar import CalendarEvent  # noqa: E402
from app.models.demand import DemandSnapshot  # noqa: E402
from app.models.district import District  # noqa: E402
from app.models.traffic import TrafficObservation  # noqa: E402
from app.models.trip import Trip  # noqa: E402
from app.models.user import User  # noqa: E402
from app.models.weather import WeatherObservation  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.providers.factory import get_llm_provider, get_traffic_provider, get_weather_provider  # noqa: E402
from app.services.ai_analysis_service import analyze_trip  # noqa: E402
from app.synth import generator as gen  # noqa: E402

_DEMO_USER_EMAIL = "demo@taxiai.local"
_TICK_TRIP_BASE_PROBABILITY = 0.10  # per 5-min tick, scaled by current demand level


def _floor_to_5min(dt: datetime) -> datetime:
    return dt.replace(minute=(dt.minute // 5) * 5, second=0, microsecond=0)


def _floor_to_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def _load_districts(session) -> list[gen.DistrictInfo]:
    districts = session.execute(select(District)).scalars().all()
    return [
        gen.DistrictInfo(d.id, d.name, float(d.centroid_lat), float(d.centroid_lng), d.airport_nearby)
        for d in districts
    ]


def _load_recent_event_windows(session, district_by_id: dict) -> list[tuple]:
    since = datetime.now(timezone.utc) - timedelta(days=3)
    rows = (
        session.execute(select(CalendarEvent).where(CalendarEvent.event_date >= since.date()))
        .scalars()
        .all()
    )
    dict_rows = [
        {"event_date": r.event_date, "event_type": r.event_type, "district_id": r.district_id}
        for r in rows
    ]
    return gen.event_windows_from_rows(dict_rows, district_by_id)


def _load_recent_arrivals(session) -> dict[str, list[datetime]]:
    since = datetime.now(timezone.utc) - timedelta(hours=2)
    rows = (
        session.execute(
            select(AirportFlight).where(
                AirportFlight.direction == "arrival",
                AirportFlight.actual_time.isnot(None),
                AirportFlight.actual_time >= since,
            )
        )
        .scalars()
        .all()
    )
    out: dict[str, list[datetime]] = {}
    for r in rows:
        out.setdefault(r.airport_code, []).append(r.actual_time)
    return out


def _current_weather(session, now_hour: datetime) -> dict:
    last = (
        session.execute(
            select(WeatherObservation).order_by(WeatherObservation.observed_at.desc()).limit(1)
        )
        .scalars()
        .first()
    )
    if last and last.observed_at == now_hour:
        return {
            "observed_at": last.observed_at,
            # .value, not the bare ORM enum instance: `class X(str, enum.Enum)`
            # members format as "X.MEMBER" in f-strings/logging on this Python
            # version, even though equality checks against plain strings still
            # work fine — caught from a genuinely confusing log line, not a
            # data-correctness bug.
            "precipitation_type": last.precipitation_type.value,
        }

    settings = get_settings()
    if settings.resolved_mode(settings.weather_provider_mode, settings.openweather_api_key) == "live":
        try:
            live_data = get_weather_provider(session).get_current()
            row = {**live_data, "observed_at": now_hour, "district_id": None, "source": "live"}
            session.execute(insert(WeatherObservation), [row])
            return row
        except Exception:
            # A live-provider hiccup (bad/not-yet-active key, network blip, rate
            # limit) shouldn't take down the whole tick — this ran early enough
            # that an uncaught exception here would also skip demand/trip
            # generation below, not just weather. Fall back to synthetic for
            # this tick and let the next tick retry live.
            logging.getLogger("taxiai.synth").warning(
                "Live weather fetch failed, falling back to synthetic for this tick", exc_info=True
            )

    state = gen.WeatherState(
        temperature_c=float(last.temperature_c) if last else gen.seasonal_baseline_temp(now_hour.date()),
        raining=(last.precipitation_type != "none") if last else False,
    )
    _, row = gen.step_weather(state, now_hour)
    session.execute(insert(WeatherObservation), [row])
    return row


def _maybe_analyze_new_trip(session, trip: Trip) -> None:
    """Generates the AI post-mortem for a freshly-inserted trip, same as a
    real driver app's trip-completion webhook would trigger."""
    try:
        analyze_trip(session, trip, get_llm_provider())
    except Exception:
        logging.getLogger("taxiai.synth").exception("Trip analysis failed for trip %s", trip.id)


def _maybe_ingest_traffic(session, districts: list[gen.DistrictInfo], now_hour: datetime) -> None:
    """Traffic is hourly-resolution by design (see synth/generator.py's
    generate_traffic); only generate/fetch once per hour, and only if this
    hour doesn't already have rows (a tick can fire multiple times within the
    same hour)."""
    existing = session.execute(
        select(TrafficObservation.id).where(TrafficObservation.observed_at == now_hour).limit(1)
    ).first()
    if existing:
        return

    settings = get_settings()
    # TomTom's free tier is 2,500 requests/day; with ~130 districts, hourly
    # polling would need 3,120/day. Fetch live on even hours only (~1,560/day)
    # and fill odd hours synthetically — traffic changes slowly enough that a
    # 2-hour live cadence keeps the ML features honest.
    live_hour = now_hour.hour % 2 == 0
    if live_hour and settings.resolved_mode(settings.traffic_provider_mode, settings.tomtom_api_key) == "live":
        try:
            provider = get_traffic_provider(session)
            rows = []
            for d in districts:
                data = provider.get_current(d.lat, d.lng)
                rows.append(
                    {
                        "observed_at": now_hour,
                        "district_id": d.id,
                        "congestion_level": data["congestion_level"],
                        "avg_speed_kmh": data.get("avg_speed_kmh"),
                        "source": "live",
                    }
                )
            session.execute(insert(TrafficObservation), rows)
            return
        except Exception:
            # Same reasoning as the weather fallback above: a bad/rate-limited
            # TomTom call shouldn't lose this hour's traffic entirely, and a
            # partial `rows` list was never inserted (the failure aborts the
            # loop before the single bulk insert), so falling back to
            # synthetic here can't create duplicate/mixed-source rows.
            logging.getLogger("taxiai.synth").warning(
                "Live traffic fetch failed, falling back to synthetic for this hour", exc_info=True
            )

    rows = gen.generate_traffic([now_hour], districts)
    session.execute(insert(TrafficObservation), rows)


def _maybe_ingest_prices(session, districts: list[gen.DistrictInfo], now: datetime) -> None:
    """Real ride-price quotes (Yandex Taxi widget API) per district, from which
    /v1/surge/current derives the live surge coefficient. Live-only: in mock
    mode /v1/surge/current falls back to demand_snapshots directly, so writing
    synthetic price rows would just duplicate that signal. Cadence is
    PRICING_POLL_MINUTES (default 30) — the key's request limits are agreed
    with Yandex individually, so the budget is configurable rather than
    hardcoded like TomTom's."""
    from app.models.pricing import PriceObservation
    from app.services.surge_service import reference_route

    settings = get_settings()
    key = settings.yandex_taxi_api_key if settings.yandex_taxi_clid else ""
    if settings.resolved_mode(settings.pricing_provider_mode, key) != "live":
        return

    last = session.execute(
        select(PriceObservation.observed_at).order_by(PriceObservation.observed_at.desc()).limit(1)
    ).scalar_one_or_none()
    if last and now - last < timedelta(minutes=settings.pricing_poll_minutes):
        return

    from app.providers.factory import get_pricing_provider

    try:
        provider = get_pricing_provider(session)
        rows = []
        for d in districts:
            to_lat, to_lng = reference_route(d.lat, d.lng)
            quote = provider.get_ride_price(d.lat, d.lng, to_lat, to_lng)
            rows.append(
                {
                    "observed_at": now,
                    "district_id": d.id,
                    "tariff_class": quote["tariff_class"],
                    "price": quote["price"],
                    "currency": quote["currency"],
                    "source": "live",
                }
            )
        session.execute(insert(PriceObservation), rows)
    except Exception:
        # No synthetic fallback here on purpose: a fabricated price row would
        # poison the rolling baseline that real quotes are divided by.
        logging.getLogger("taxiai.synth").warning(
            "Live price fetch failed; skipping this pricing tick", exc_info=True
        )


def _maybe_insert_flight(session, airport_code: str, now: datetime) -> None:
    settings = get_settings()
    if settings.resolved_mode(settings.flights_provider_mode, settings.aviationstack_api_key) == "live":
        # Real flights come from the daily app/jobs/ingest_flights.py instead —
        # AviationStack's free tier is only ~100 requests/month, nowhere near
        # enough for a 5-min tick, so don't also lay synthetic flights on top.
        return

    last = (
        session.execute(
            select(AirportFlight)
            .where(AirportFlight.airport_code == airport_code)
            .order_by(AirportFlight.scheduled_time.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )
    # Roughly one flight every ~15 min per airport; a 5-min tick fires ~1/3 of the time.
    if gen.rng.random() > 0.33:
        return
    direction = "departure" if (last and last.direction == "arrival") else "arrival"
    status, delay_minutes, actual_time = "on_time", None, now
    roll = gen.rng.random()
    if roll < 0.01:
        status, actual_time = "cancelled", None
    elif roll < 0.09:
        status = "delayed"
        delay_minutes = gen.rng.randint(10, 45)
        actual_time = now + timedelta(minutes=delay_minutes)
    elif direction == "arrival":
        status = "landed"
    session.execute(
        insert(AirportFlight),
        [
            {
                "airport_code": airport_code,
                "scheduled_time": now,
                "actual_time": actual_time,
                "direction": direction,
                "status": status,
                "delay_minutes": delay_minutes,
                "source": "synthetic",
            }
        ],
    )


def run_tick() -> None:
    session = SessionLocal()
    try:
        now = _floor_to_5min(datetime.now(timezone.utc))
        now_hour = _floor_to_hour(now)

        districts = _load_districts(session)
        if not districts:
            print("No districts seeded yet; skipping tick.")
            return
        district_by_id = {d.id: d for d in districts}

        demo_user = session.execute(select(User).where(User.email == _DEMO_USER_EMAIL)).scalar_one_or_none()

        weather_row = _current_weather(session, now_hour)
        _maybe_ingest_traffic(session, districts, now_hour)
        _maybe_ingest_prices(session, districts, now)

        for code in ["SVO", "VKO", "DME"]:
            _maybe_insert_flight(session, code, now)

        ctx = gen.GeneratorContext(districts=districts)
        ctx.event_windows = _load_recent_event_windows(session, district_by_id)
        ctx.arrival_times_by_airport = _load_recent_arrivals(session)

        demand_rows = []
        levels_by_district: dict[int, float] = {}
        for d in districts:
            level, surge = gen.demand_for_slot(ctx, d, now, weather_row)
            levels_by_district[d.id] = level
            demand_rows.append(
                {
                    "district_id": d.id,
                    "observed_at": now,
                    "demand_level": level,
                    "surge_multiplier": surge,
                    "active_orders_estimate": int(level * 40),
                    "free_drivers_estimate": int((1 - level) * 25) + 3,
                    "source": "synthetic",
                }
            )
        session.execute(insert(DemandSnapshot), demand_rows)

        new_trip = None
        if demo_user and gen.rng.random() < _TICK_TRIP_BASE_PROBABILITY:
            weighted = [(did, max(lvl, 0.05)) for did, lvl in levels_by_district.items()]
            (district_id,) = gen.rng.choices(
                [w[0] for w in weighted], weights=[w[1] for w in weighted], k=1
            )
            demand_map = {(district_id, now.hour): levels_by_district[district_id]}
            trip_rows = gen.generate_trips_for_day(
                ctx, now.date(), districts, demand_map, {now_hour: weather_row}, demo_user.id, 1
            )
            for row in trip_rows:
                row["id"] = uuid.uuid4()
                row["start_time"] = now
                row["end_time"] = now + timedelta(seconds=row["duration_seconds"])
            if trip_rows:
                new_trip = Trip(**trip_rows[0])
                session.add(new_trip)

        session.commit()

        if new_trip is not None:
            _maybe_analyze_new_trip(session, new_trip)
        precip = weather_row.get("precipitation_type", "n/a")
        print(f"[{now.isoformat()}] tick: {len(demand_rows)} demand rows, weather={precip}")
    finally:
        session.close()


if __name__ == "__main__":
    run_tick()
