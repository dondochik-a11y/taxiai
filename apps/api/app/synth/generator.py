"""Core synthetic-data generation logic, shared by the one-off 90-day backfill
(scripts/seed_synthetic_history.py) and the ongoing every-5-min live tick
(scripts/simulate_live_feed.py). Both call the same functions here so real
ingestion can later replace only the call site, not this signal logic.

All timestamps are timezone-aware UTC.
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from app.synth import signal_config as cfg

_rng = random.Random(cfg.RANDOM_SEED)
rng = _rng  # public alias for reuse by scripts/simulate_live_feed.py


@dataclass
class DistrictInfo:
    id: int
    name: str
    lat: float
    lng: float
    airport_nearby: bool


@dataclass
class WeatherState:
    temperature_c: float
    raining: bool = False
    rain_remaining_hours: int = 0


@dataclass
class GeneratorContext:
    """Precomputed lookups needed to score demand at any (district, timestamp)."""

    districts: list[DistrictInfo]
    district_by_name: dict[str, DistrictInfo] = field(init=False)
    weather_by_hour: dict[datetime, dict] = field(default_factory=dict)
    event_windows: list[tuple[datetime, datetime, str]] = field(default_factory=list)
    arrival_times_by_airport: dict[str, list[datetime]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.district_by_name = {d.name: d for d in self.districts}


AIRPORT_DISTRICT_TO_CODE = dict(
    zip(cfg.AIRPORT_DISTRICTS, ["SVO", "VKO", "DME"], strict=True)
)


def _hour_floor(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def seasonal_baseline_temp(d: date) -> float:
    """Rough Moscow seasonal curve: coldest ~mid-January, warmest ~mid-July."""
    day_of_year = d.timetuple().tm_yday
    phase = (day_of_year - 15) / 365.0 * 2 * math.pi
    return 5.0 - 18.0 * math.cos(phase)


def step_weather(state: WeatherState, dt: datetime) -> tuple[WeatherState, dict]:
    """Advance the weather random walk by one hour and return the new state
    plus a weather_observations row (city-wide, district_id=None)."""
    baseline = seasonal_baseline_temp(dt.date())
    drift = _rng.gauss(0, 0.6)
    temperature_c = round(0.85 * state.temperature_c + 0.15 * baseline + drift, 1)

    raining = state.raining
    rain_remaining = state.rain_remaining_hours
    if raining:
        rain_remaining -= 1
        if rain_remaining <= 0:
            raining = False
    elif _rng.random() < 0.05:
        raining = True
        rain_remaining = _rng.randint(2, 5)

    precipitation_type = "none"
    precipitation_mm = 0.0
    if raining:
        precipitation_type = "snow" if temperature_c <= 0 else "rain"
        precipitation_mm = round(max(0.1, _rng.gauss(1.5, 0.8)), 2)

    wind_speed_ms = round(max(0.0, _rng.gauss(4.0, 2.0)), 1)

    new_state = WeatherState(temperature_c, raining, rain_remaining)
    row = {
        "observed_at": dt,
        "district_id": None,
        "temperature_c": temperature_c,
        "precipitation_type": precipitation_type,
        "precipitation_mm": precipitation_mm,
        "wind_speed_ms": wind_speed_ms,
        "condition_text": precipitation_type if precipitation_type != "none" else "clear",
        "source": "synthetic",
    }
    return new_state, row


def generate_calendar_events(start: date, end: date, districts: list[DistrictInfo]) -> list[dict]:
    rows: list[dict] = []
    d = start
    while d <= end:
        if d.weekday() >= 5:
            rows.append(
                {
                    "event_date": d,
                    "event_type": "weekend",
                    "title": "Weekend",
                    "district_id": None,
                    "expected_impact": "low",
                    "source": "synthetic",
                }
            )
        if (d.month, d.day) in cfg.FIXED_RUSSIAN_HOLIDAYS:
            rows.append(
                {
                    "event_date": d,
                    "event_type": "public_holiday",
                    "title": "Public holiday",
                    "district_id": None,
                    "expected_impact": "medium",
                    "source": "synthetic",
                }
            )
        d += timedelta(days=1)

    event_district = districts and next(
        (x for x in districts if x.name == cfg.EVENT_DISTRICT), None
    )
    # Procedurally place a football match on ~1 in 3 Saturdays, a concert on ~1 in 4 Sundays.
    d = start
    while d <= end:
        if d.weekday() == 5 and _rng.random() < 0.33 and event_district:
            rows.append(
                {
                    "event_date": d,
                    "event_type": "football_match",
                    "title": "Football match",
                    "district_id": event_district.id,
                    "expected_impact": "high",
                    "source": "synthetic",
                }
            )
        if d.weekday() == 6 and _rng.random() < 0.25:
            other = _rng.choice(districts)
            rows.append(
                {
                    "event_date": d,
                    "event_type": "concert",
                    "title": "Concert / mass event",
                    "district_id": other.id,
                    "expected_impact": "medium",
                    "source": "synthetic",
                }
            )
        d += timedelta(days=1)
    return rows


def event_windows_from_rows(rows: list[dict], district_by_id: dict[int, DistrictInfo]) -> list[tuple]:
    windows = []
    for r in rows:
        if r["event_type"] not in ("football_match", "concert", "mass_event") or r["district_id"] is None:
            continue
        district = district_by_id.get(r["district_id"])
        if district is None:
            continue
        evt_dt = datetime.combine(r["event_date"], datetime.min.time(), tzinfo=timezone.utc) + timedelta(
            hours=19
        )
        windows.append(
            (
                evt_dt - timedelta(hours=cfg.EVENT_WINDOW_HOURS),
                evt_dt + timedelta(hours=cfg.EVENT_WINDOW_HOURS),
                district.name,
            )
        )
    return windows


def generate_airport_flights(start: datetime, end: datetime) -> list[dict]:
    rows: list[dict] = []
    for airport_code in ["SVO", "VKO", "DME"]:
        t = start
        direction_toggle = 0
        while t < end:
            direction = "arrival" if direction_toggle % 2 == 0 else "departure"
            direction_toggle += 1
            status = "on_time"
            delay_minutes = None
            actual_time = t
            if _rng.random() < 0.01:
                status = "cancelled"
                actual_time = None
            elif _rng.random() < 0.08:
                status = "delayed"
                delay_minutes = _rng.randint(10, 45)
                actual_time = t + timedelta(minutes=delay_minutes)
            elif direction == "arrival":
                status = "landed"

            rows.append(
                {
                    "airport_code": airport_code,
                    "scheduled_time": t,
                    "actual_time": actual_time,
                    "direction": direction,
                    "status": status,
                    "delay_minutes": delay_minutes,
                    "source": "synthetic",
                }
            )
            t += timedelta(minutes=_rng.randint(12, 18))
    return rows


def generate_metro_incidents(start: datetime, end: datetime) -> list[dict]:
    lines = ["Сокольническая", "Замоскворецкая", "Арбатско-Покровская", "Кольцевая", "Таганско-Краснопресненская"]
    rows: list[dict] = []
    span_days = (end - start).days
    n_incidents = max(1, span_days // 12)  # roughly one every ~12 days
    for _ in range(n_incidents):
        started_at = start + timedelta(seconds=_rng.uniform(0, (end - start).total_seconds()))
        duration_hours = _rng.uniform(0.5, 6)
        rows.append(
            {
                "line_name": _rng.choice(lines),
                "station_name": None,
                "incident_type": _rng.choice(["repair", "delay", "incident"]),
                "started_at": started_at,
                "resolved_at": started_at + timedelta(hours=duration_hours),
                "description": "Synthetic incident for MVP demo data",
                "source": "synthetic",
            }
        )
    return rows


def _traffic_congestion(hour: int, is_center: bool, is_weekend: bool) -> float:
    rush = max(cfg.HOURLY_BASE_DEMAND[hour], cfg.HOURLY_BASE_DEMAND[(hour + 1) % 24]) * 10
    if is_weekend:
        rush *= 0.7
    if is_center:
        rush += 1.5
    rush += _rng.gauss(0, 0.8)
    return round(min(10.0, max(0.0, rush)), 1)


def generate_traffic(hours: list[datetime], districts: list[DistrictInfo]) -> list[dict]:
    rows: list[dict] = []
    center_names = set(cfg.CENTER_DISTRICTS)
    for dt in hours:
        is_weekend = dt.weekday() >= 5
        for d in districts:
            level = _traffic_congestion(dt.hour, d.name in center_names, is_weekend)
            rows.append(
                {
                    "observed_at": dt,
                    "district_id": d.id,
                    "congestion_level": level,
                    "avg_speed_kmh": round(max(5.0, 60 - level * 4.5), 1),
                    "source": "synthetic",
                }
            )
    return rows


def _arrival_density_boost(ctx: GeneratorContext, district_name: str, dt: datetime) -> float:
    code = AIRPORT_DISTRICT_TO_CODE.get(district_name)
    if code is None:
        return 0.0
    times = ctx.arrival_times_by_airport.get(code, [])
    if not times:
        return 0.0
    window_start = dt - timedelta(minutes=cfg.AIRPORT_ARRIVAL_WINDOW_MINUTES)
    count = sum(1 for t in times if window_start <= t <= dt)
    # Normalize: ~4 arrivals in the window is treated as "busy".
    return min(1.0, count / 4.0) * cfg.AIRPORT_ARRIVAL_DEMAND_WEIGHT


def _in_event_window(ctx: GeneratorContext, district_name: str, dt: datetime) -> bool:
    if district_name != cfg.EVENT_DISTRICT:
        return False
    return any(start <= dt <= end for start, end, name in ctx.event_windows if name == district_name)


def demand_for_slot(
    ctx: GeneratorContext, district: DistrictInfo, dt: datetime, weather_row: dict | None
) -> tuple[float, float]:
    """Returns (demand_level 0..1, surge_multiplier)."""
    base = cfg.HOURLY_BASE_DEMAND[dt.hour]
    base *= cfg.DOW_MULTIPLIER[dt.weekday()]
    if dt.weekday() == 6 and 6 <= dt.hour < 12:
        base *= cfg.SUNDAY_MORNING_DAMPENER

    is_raining = bool(weather_row and weather_row["precipitation_type"] != "none")
    if is_raining and district.name in cfg.RAIN_BOOST_DISTRICTS:
        base *= cfg.RAIN_BOOST_MULTIPLIER

    if district.airport_nearby:
        base += _arrival_density_boost(ctx, district.name, dt)

    if _in_event_window(ctx, district.name, dt):
        base += cfg.EVENT_DEMAND_BOOST

    if dt.weekday() == 4 and dt.hour >= cfg.FRIDAY_LATE_HOUR:
        if district.name in cfg.CENTER_DISTRICTS:
            base *= cfg.FRIDAY_CENTER_DISCOUNT
        elif district.airport_nearby:
            base *= cfg.FRIDAY_AIRPORT_BOOST

    base += _rng.gauss(0, cfg.DEMAND_NOISE_STD)
    demand_level = min(1.0, max(0.0, base))
    surge_multiplier = round(1.0 + demand_level * 1.8, 2)
    return round(demand_level, 3), surge_multiplier


def build_context(
    districts: list[DistrictInfo],
    calendar_rows: list[dict],
    flight_rows: list[dict],
    district_by_id: dict[int, DistrictInfo],
) -> GeneratorContext:
    ctx = GeneratorContext(districts=districts)
    ctx.event_windows = event_windows_from_rows(calendar_rows, district_by_id)
    arrivals: dict[str, list[datetime]] = {}
    for f in flight_rows:
        if f["direction"] != "arrival" or f["actual_time"] is None:
            continue
        arrivals.setdefault(f["airport_code"], []).append(f["actual_time"])
    for code, times in arrivals.items():
        times.sort()
    ctx.arrival_times_by_airport = arrivals
    return ctx


_BASE_FARE = 150.0
_PER_KM = 22.0
_PER_MINUTE = 8.0


def generate_trips_for_day(
    ctx: GeneratorContext,
    day: date,
    districts: list[DistrictInfo],
    demand_by_district_hour: dict[tuple[int, int], float],
    weather_by_hour_lookup: dict[datetime, dict],
    user_id,
    trips_target: int,
) -> list[dict]:
    """Sample `trips_target` trips across the day, weighted toward higher-demand
    (district, hour) slots so the finance layer shares the same underlying signal
    as demand_snapshots."""
    weighted_slots: list[tuple[int, int, float]] = []
    for (district_id, hour), level in demand_by_district_hour.items():
        weighted_slots.append((district_id, hour, max(level, 0.05)))
    if not weighted_slots:
        return []

    weights = [w for *_ignore, w in weighted_slots]
    chosen = _rng.choices(weighted_slots, weights=weights, k=trips_target)

    district_by_id = {d.id: d for d in districts}
    rows: list[dict] = []
    for district_id, hour, level in chosen:
        start_district = district_by_id[district_id]
        end_district = _rng.choice(districts)
        surge = round(1.0 + level * 1.8, 2)

        minute = _rng.randint(0, 59)
        start_time = datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc) + timedelta(
            hours=hour, minutes=minute
        )

        distance_km = round(max(1.0, _rng.gauss(9.0, 5.0)), 2)
        duration_seconds = int(distance_km * 60 / _rng.uniform(0.35, 0.55))  # ~25-40 km/h effective
        end_time = start_time + timedelta(seconds=duration_seconds)

        # Higher demand -> shorter wait for the driver (more passengers available).
        wait_time_seconds = int(max(30, _rng.gauss(240 - level * 150, 60)))
        time_to_pickup_seconds = int(max(30, _rng.gauss(300 - level * 150, 90)))

        price = _BASE_FARE + distance_km * _PER_KM + (duration_seconds / 60) * _PER_MINUTE
        price *= surge
        price *= 1 + _rng.gauss(0, cfg.TRIP_PRICE_NOISE_STD)
        price = round(max(_BASE_FARE, price), 2)

        rows.append(
            {
                "user_id": user_id,
                "start_time": start_time,
                "end_time": end_time,
                "start_district_id": start_district.id,
                "end_district_id": end_district.id,
                "start_lat": start_district.lat,
                "start_lng": start_district.lng,
                "end_lat": end_district.lat,
                "end_lng": end_district.lng,
                "time_to_pickup_seconds": time_to_pickup_seconds,
                "wait_time_seconds": wait_time_seconds,
                "distance_km": distance_km,
                "duration_seconds": duration_seconds,
                "price": price,
                "tariff": "economy",
                "surge_multiplier_at_start": surge,
                "weather_id": None,
                "source": "synthetic",
            }
        )
    return rows
