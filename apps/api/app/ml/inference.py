"""Loads the trained demand model and populates the forecasts table for every
district across all horizons. surge/avg-check/wait-time are derived
analytically from the predicted demand_level using the same formulas the
synthetic trip generator uses (app/synth/generator.py) — kept consistent and
simple rather than training separate, data-starved regressors for them (trips
are sparse per district/hour, which would make a real price/wait regressor
noisy at this data volume).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import joblib
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ml import features as feat
from app.models.district import District
from app.models.forecast import Forecast

ARTIFACTS_DIR = Path(__file__).resolve().parent / "artifacts"
MODEL_PATH = ARTIFACTS_DIR / "demand_model.joblib"

# Mirrors app/synth/generator.py's own formulas so forecasts stay consistent
# with how the underlying synthetic (or later, real) trip economics behave.
_BASE_FARE = 150.0
_PER_KM = 22.0
_AVG_TRIP_KM = 9.0
_SURGE_SLOPE = 1.8

# Keyed by the artifact file's mtime: the worker is a long-lived process, and
# a plain "load once" cache would keep serving the old model forever after the
# weekly retrain job replaces the file.
_artifact_cache: dict | None = None
_artifact_mtime: float | None = None


def _load_artifact() -> dict:
    global _artifact_cache, _artifact_mtime
    if not MODEL_PATH.exists():
        raise RuntimeError(f"No trained model at {MODEL_PATH} — run `make train` first.")
    mtime = MODEL_PATH.stat().st_mtime
    if _artifact_cache is None or mtime != _artifact_mtime:
        _artifact_cache = joblib.load(MODEL_PATH)
        _artifact_mtime = mtime
    return _artifact_cache


def _surge_from_demand(demand_level: float) -> float:
    return round(1.0 + demand_level * _SURGE_SLOPE, 2)


def _avg_check_from_surge(surge: float) -> float:
    return round((_BASE_FARE + _AVG_TRIP_KM * _PER_KM) * surge, 2)


def _wait_seconds_from_demand(demand_level: float) -> int:
    return int(max(30, 240 - demand_level * 150))


def generate_forecasts(session: Session, horizons: list[int] = feat.HORIZONS_MINUTES) -> list[Forecast]:
    artifact = _load_artifact()
    model = artifact["model"]
    columns = artifact["feature_columns"]
    district_ids = artifact["district_ids"]
    model_version = artifact["model_version"]

    now = datetime.now(timezone.utc)
    lookback_start = now - timedelta(days=9)  # covers the 168h (7-day) lag feature plus margin

    demand_df = feat.load_demand(since=lookback_start)
    if demand_df.empty:
        raise RuntimeError("No recent demand_snapshots — is the worker's live feed tick running?")
    weather_df = feat.load_weather_hourly(since=lookback_start)
    traffic_df = feat.load_traffic(since=lookback_start)
    calendar_df = feat.load_calendar(since=lookback_start.date())
    districts_df = pd.read_sql(select(District.id, District.name, District.airport_nearby), session.bind)

    feature_df = feat.build_features(demand_df, weather_df, traffic_df, calendar_df, districts_df)
    feature_df = feat.add_district_dummies(feature_df, district_ids)

    # t0 (the latest available demand_snapshot) anchors both generated_at and
    # target_time. Using wall-clock `now` for generated_at instead would let
    # target_time (t0 + horizon) drift into the past relative to it whenever
    # the worker's live-feed tick lags a few minutes behind — confusing for
    # API consumers even though the forecast itself is still valid.
    t0 = feature_df["observed_at"].max()
    current = feature_df[feature_df["observed_at"] == t0].drop_duplicates(subset=["district_id"])

    forecasts: list[Forecast] = []
    for horizon in horizons:
        batch = current.copy()
        batch["horizon_minutes"] = horizon
        preds = model.predict(batch[columns])
        target_time = t0 + timedelta(minutes=horizon)
        for district_id, pred in zip(batch["district_id"], preds):
            demand_level = float(min(1.0, max(0.0, pred)))
            surge = _surge_from_demand(demand_level)
            forecasts.append(
                Forecast(
                    district_id=int(district_id),
                    generated_at=t0,
                    horizon_minutes=horizon,
                    target_time=target_time,
                    predicted_demand_level=round(demand_level, 3),
                    predicted_surge=surge,
                    predicted_avg_check=_avg_check_from_surge(surge),
                    predicted_wait_time_seconds=_wait_seconds_from_demand(demand_level),
                    model_version=model_version,
                )
            )

    session.add_all(forecasts)
    session.commit()
    return forecasts
