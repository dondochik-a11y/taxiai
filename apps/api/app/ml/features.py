"""Feature engineering shared by train_demand_model.py and inference.py so
there's no train/serve skew — both call build_features() on whatever raw rows
they have (historical DataFrame at train time, a single "now" snapshot built
from the latest DB rows at inference time).
"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

from app.db.session import engine
from app.models.calendar import CalendarEvent
from app.models.demand import DemandSnapshot
from app.models.district import District
from app.models.traffic import TrafficObservation
from app.models.weather import WeatherObservation

HORIZONS_MINUTES = [15, 30, 60, 120]
LAG_HOURS = [1, 24, 168]  # 1h, 1 day, 1 week

_EVENT_TYPES = {"football_match", "concert", "mass_event"}


def load_demand(since: datetime | None = None) -> pd.DataFrame:
    stmt = select(DemandSnapshot.district_id, DemandSnapshot.observed_at, DemandSnapshot.demand_level)
    if since is not None:
        stmt = stmt.where(DemandSnapshot.observed_at >= since)
    df = pd.read_sql(stmt, engine, parse_dates=["observed_at"])
    df["demand_level"] = df["demand_level"].astype(float)
    return df


def load_weather_hourly(since: datetime | None = None) -> pd.DataFrame:
    stmt = select(
        WeatherObservation.observed_at,
        WeatherObservation.temperature_c,
        WeatherObservation.precipitation_type,
        WeatherObservation.wind_speed_ms,
    )
    if since is not None:
        stmt = stmt.where(WeatherObservation.observed_at >= since)
    df = pd.read_sql(stmt, engine, parse_dates=["observed_at"])
    df["temperature_c"] = df["temperature_c"].astype(float)
    df["wind_speed_ms"] = df["wind_speed_ms"].astype(float)
    df["is_precipitation"] = (df["precipitation_type"] != "none").astype(int)
    return df.drop(columns=["precipitation_type"])


def load_traffic(since: datetime | None = None) -> pd.DataFrame:
    stmt = select(
        TrafficObservation.district_id, TrafficObservation.observed_at, TrafficObservation.congestion_level
    )
    if since is not None:
        stmt = stmt.where(TrafficObservation.observed_at >= since)
    df = pd.read_sql(stmt, engine, parse_dates=["observed_at"])
    df["congestion_level"] = df["congestion_level"].astype(float)
    return df


def load_calendar(since: date | None = None) -> pd.DataFrame:
    stmt = select(CalendarEvent.event_date, CalendarEvent.event_type, CalendarEvent.district_id)
    if since is not None:
        stmt = stmt.where(CalendarEvent.event_date >= since)
    df = pd.read_sql(stmt, engine)
    return df


def load_districts() -> pd.DataFrame:
    return pd.read_sql(select(District.id, District.name, District.airport_nearby), engine)


def _cyclical(value: float, period: float) -> tuple[float, float]:
    angle = 2 * math.pi * value / period
    return math.sin(angle), math.cos(angle)


def _demand_lookup(df: pd.DataFrame) -> pd.Series:
    """(district_id, observed_at) -> demand_level with a unique index, so
    reindex() can use the fast hash path (it raises on duplicate labels)."""
    return (
        df.drop_duplicates(subset=["district_id", "observed_at"])
        .set_index(["district_id", "observed_at"])["demand_level"]
    )


def build_features(
    demand_df: pd.DataFrame,
    weather_df: pd.DataFrame,
    traffic_df: pd.DataFrame,
    calendar_df: pd.DataFrame,
    districts_df: pd.DataFrame,
) -> pd.DataFrame:
    """One row per (district_id, observed_at) with every model feature plus the
    current demand_level (used both as a feature source for lags and, at
    inference time, ignored in favor of the model's own prediction)."""
    df = demand_df.copy()
    df["hour_floor"] = df["observed_at"].dt.floor("h")

    weather = weather_df.rename(columns={"observed_at": "hour_floor"})
    df = df.merge(weather, on="hour_floor", how="left")

    traffic = traffic_df.rename(columns={"observed_at": "hour_floor"})
    df = df.merge(traffic, on=["district_id", "hour_floor"], how="left")

    df = df.merge(districts_df.rename(columns={"id": "district_id"}), on="district_id", how="left")

    holiday_dates = set(calendar_df.loc[calendar_df["event_type"] == "public_holiday", "event_date"])
    event_pairs = set(
        zip(
            calendar_df.loc[calendar_df["event_type"].isin(_EVENT_TYPES), "district_id"],
            calendar_df.loc[calendar_df["event_type"].isin(_EVENT_TYPES), "event_date"],
        )
    )

    df["date"] = df["observed_at"].dt.date
    df["is_weekend"] = (df["observed_at"].dt.weekday >= 5).astype(int)
    df["is_holiday"] = df["date"].isin(holiday_dates).astype(int)
    df["is_event_today"] = [
        1 if (did, d) in event_pairs else 0 for did, d in zip(df["district_id"], df["date"])
    ]

    hour_sin_cos = df["observed_at"].dt.hour.apply(lambda h: _cyclical(h, 24))
    df["hour_sin"] = hour_sin_cos.apply(lambda t: t[0])
    df["hour_cos"] = hour_sin_cos.apply(lambda t: t[1])
    dow_sin_cos = df["observed_at"].dt.weekday.apply(lambda d: _cyclical(d, 7))
    df["dow_sin"] = dow_sin_cos.apply(lambda t: t[0])
    df["dow_cos"] = dow_sin_cos.apply(lambda t: t[1])

    # Vectorized reindex on a unique MultiIndex uses the hash engine; the
    # previous per-key `lookup.get(...)` list comprehension degraded to a
    # linear scan per key on the unsorted index — unnoticeable at 20 districts,
    # effectively infinite at 130 (~5M keys × 760k rows).
    lookup = _demand_lookup(df)
    for lag_h in LAG_HOURS:
        delta = timedelta(hours=lag_h)
        shifted = pd.MultiIndex.from_arrays([df["district_id"], df["observed_at"] - delta])
        df[f"lag_{lag_h}h"] = lookup.reindex(shifted).to_numpy()
        df[f"lag_{lag_h}h"] = df[f"lag_{lag_h}h"].fillna(df["demand_level"].mean())

    df["temperature_c"] = df["temperature_c"].fillna(df["temperature_c"].mean())
    df["is_precipitation"] = df["is_precipitation"].fillna(0)
    df["wind_speed_ms"] = df["wind_speed_ms"].fillna(0)
    df["congestion_level"] = df["congestion_level"].fillna(df["congestion_level"].mean())
    df["airport_nearby"] = df["airport_nearby"].fillna(False).astype(int)

    return df


def shift_clock_features(df: pd.DataFrame, horizon_minutes: int) -> pd.DataFrame:
    """Recompute the clock features at the forecast TARGET time (observed_at +
    horizon), in place. Without this every horizon sees identical "now" clock
    features and the model has to reconstruct the phase shift from
    horizon_minutes alone — which trees barely do, so forecasts came out nearly
    flat across horizons. horizon_minutes stays a feature: it still encodes how
    stale the lag features are. Date-based flags (is_holiday/is_event_today)
    are left at the observation date — a horizon crossing midnight is a
    rounding error at ≤2h. Both training and inference must route every
    per-horizon frame through here, or the clock conventions skew."""
    target = df["observed_at"] + timedelta(minutes=horizon_minutes)
    hour = target.dt.hour + target.dt.minute / 60.0
    h_angle = 2 * np.pi * hour / 24.0
    dow = target.dt.weekday
    d_angle = 2 * np.pi * dow / 7.0
    df["hour_sin"] = np.sin(h_angle)
    df["hour_cos"] = np.cos(h_angle)
    df["dow_sin"] = np.sin(d_angle)
    df["dow_cos"] = np.cos(d_angle)
    df["is_weekend"] = (dow >= 5).astype(int)
    return df


def district_dummy_columns(district_ids: list[int]) -> list[str]:
    return [f"district_{d}" for d in sorted(district_ids)]


def add_district_dummies(df: pd.DataFrame, district_ids: list[int]) -> pd.DataFrame:
    """One-hot district identity — without this the model has no way to tell
    apart e.g. Павелецкая/Курская (the rain-boost districts) from any other
    district, since airport_nearby/weather/traffic are otherwise shared or
    city-wide."""
    dummies = pd.DataFrame(
        {f"district_{did}": (df["district_id"] == did).astype(np.int8) for did in district_ids},
        index=df.index,
    )
    return pd.concat([df, dummies], axis=1)


NUMERIC_FEATURE_COLUMNS = [
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "is_weekend",
    "is_holiday",
    "is_event_today",
    "temperature_c",
    "is_precipitation",
    "wind_speed_ms",
    "congestion_level",
    "airport_nearby",
    "lag_1h",
    "lag_24h",
    "lag_168h",
    "horizon_minutes",
]


def make_training_set(
    feature_df: pd.DataFrame, district_ids: list[int], horizons: list[int] = HORIZONS_MINUTES
) -> pd.DataFrame:
    """Builds one row per (district, observed_at, horizon) with a label looked
    up at observed_at + horizon. Rows without an exact future match (e.g. a
    15-min horizon during the hourly-only portion of the backfill) are dropped
    — this naturally biases short-horizon training data toward the recent
    high-resolution window, which is fine for an MVP model."""
    feature_df = add_district_dummies(feature_df, district_ids)
    # Keep only the columns training consumes — the 4-horizon concat below
    # quadruples the frame, and dragging along geometry/name columns at 130
    # districts costs gigabytes.
    keep = ["district_id", "observed_at", "demand_level"] + [
        c for c in feature_columns_for(district_ids) if c in feature_df.columns
    ]
    feature_df = feature_df[keep]
    lookup = _demand_lookup(feature_df)
    frames = []
    for horizon in horizons:
        delta = timedelta(minutes=horizon)
        sub = feature_df.copy()
        sub["horizon_minutes"] = horizon
        sub = shift_clock_features(sub, horizon)
        future = pd.MultiIndex.from_arrays([sub["district_id"], sub["observed_at"] + delta])
        sub["label"] = lookup.reindex(future).to_numpy()
        sub = sub.dropna(subset=["label"])
        frames.append(sub)
    return pd.concat(frames, ignore_index=True)


def feature_columns_for(district_ids: list[int]) -> list[str]:
    return NUMERIC_FEATURE_COLUMNS + district_dummy_columns(district_ids)
