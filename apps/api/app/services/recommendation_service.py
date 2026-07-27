"""Turns forecast output + the driver's current location into a concrete
"stay or move" recommendation. Distances/drive-times are approximated via
haversine distance + an assumed average city speed rather than a real routing
API (no Yandex Maps key exists yet) — good enough to decide reachability
within a forecast horizon and to estimate repositioning fuel cost.
"""
from __future__ import annotations

import math
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.district import District
from app.models.forecast import Forecast
from app.models.pattern_insight import PatternInsight
from app.models.recommendation import Recommendation
from app.models.user import DriverProfile
from app.providers.base import MapsProvider

AVG_CITY_SPEED_KMH = 25.0
MOVE_THRESHOLD_PCT = 15.0  # only recommend moving if the gain clears this margin
EARTH_RADIUS_KM = 6371.0


def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _drive_minutes(distance_km: float) -> float:
    return distance_km / AVG_CITY_SPEED_KMH * 60


def _latest_forecast_by_district(session: Session, horizon_minutes: int) -> dict[int, Forecast]:
    rows = (
        session.execute(
            select(Forecast)
            .where(Forecast.horizon_minutes == horizon_minutes)
            .order_by(Forecast.district_id, Forecast.generated_at.desc())
        )
        .scalars()
        .all()
    )
    best: dict[int, Forecast] = {}
    for f in rows:
        best.setdefault(f.district_id, f)  # first hit per district_id is the most recent (query is ordered)
    return best


def _compute_uplift_pct(current_value: float, best_value: float) -> float:
    """Percent income uplift of the best reachable district over staying put.
    Same formula that gates the move decision (see MOVE_THRESHOLD_PCT) — we now
    surface it instead of throwing it away. When staying earns nothing we can't
    form a ratio, so a nonzero best counts as a full (100%) uplift."""
    if current_value > 0:
        return (best_value - current_value) / current_value * 100
    return 100.0


def _resolve_move(
    current_value: float, best_value: float, is_different_district: bool
) -> tuple[str, float | None]:
    """Decide stay/move and the uplift to advertise. Uplift is None for a stay:
    staying is the baseline, so there's no honest "+X%" to show (a below-threshold
    gain isn't worth the driver acting on and would overstate the benefit)."""
    if not is_different_district:
        return "stay", None
    gain_pct = _compute_uplift_pct(current_value, best_value)
    if gain_pct >= MOVE_THRESHOLD_PCT:
        return "move", round(gain_pct, 1)
    return "stay", None


def _valid_until(forecast: Forecast | None) -> datetime | None:
    """How long the recommendation holds. It's built on a single forecast, and
    that forecast's target_time (= generated_at + horizon_minutes) is the moment
    the predicted conditions arrive — past it the answer is stale and should be
    recomputed. Truthful and already stored on the forecast, so no guessing."""
    return forecast.target_time if forecast else None


def _matching_pattern_text(session: Session, district_name: str) -> str | None:
    rows = session.execute(select(PatternInsight)).scalars().all()
    for p in rows:
        if p.condition_json.get("district") == district_name:
            return p.pattern_text
    return None


def _build_rationale(current: District, target: District, forecast: Forecast | None, action: str, session: Session) -> str:
    if forecast is None:
        return "Недостаточно данных для прогноза в этом районе."
    # demand_level is a 0–1 model index, not a calibrated order probability —
    # surface it as an honest "уровень спроса", never as «вероятность заказа».
    demand_pct = float(forecast.predicted_demand_level) * 100
    check = float(forecast.predicted_avg_check)
    if action == "move":
        base = (
            f"Через {forecast.horizon_minutes} мин в районе «{target.name}» ожидается повышенный спрос "
            f"(уровень спроса {demand_pct:.0f}%), средний чек ≈{check:.0f} ₽ — стоит переехать."
        )
        extra = _matching_pattern_text(session, target.name)
        return f"{base} {extra}" if extra else base
    return (
        f"Оставайтесь в районе «{current.name}»: через {forecast.horizon_minutes} мин здесь ожидается спрос "
        f"с уровнем {demand_pct:.0f}%, средний чек ≈{check:.0f} ₽."
    )


def generate_recommendation(
    session: Session,
    user_id: uuid.UUID,
    lat: float,
    lng: float,
    maps_provider: MapsProvider,
    horizon_minutes: int = 30,
) -> Recommendation:
    current_district_id = maps_provider.geocode(lat, lng)
    if current_district_id is None:
        raise ValueError("Could not resolve current location to a known district")

    districts = {d.id: d for d in session.execute(select(District)).scalars().all()}
    current = districts[current_district_id]

    forecasts_by_district = _latest_forecast_by_district(session, horizon_minutes)
    profile = session.execute(
        select(DriverProfile).where(DriverProfile.user_id == user_id)
    ).scalar_one_or_none()
    fuel_cost_per_km = 0.0
    if profile:
        fuel_cost_per_km = (
            float(profile.fuel_consumption_l_per_100km) / 100 * float(profile.fuel_price_per_liter)
        )

    current_forecast = forecasts_by_district.get(current_district_id)
    current_value = (
        float(current_forecast.predicted_demand_level) * float(current_forecast.predicted_avg_check)
        if current_forecast
        else 0.0
    )

    best_district_id = current_district_id
    best_value = current_value
    best_forecast = current_forecast

    for district_id, forecast in forecasts_by_district.items():
        if district_id == current_district_id:
            continue
        candidate = districts[district_id]
        distance_km = _haversine_km(
            float(current.centroid_lat), float(current.centroid_lng),
            float(candidate.centroid_lat), float(candidate.centroid_lng),
        )
        if _drive_minutes(distance_km) > horizon_minutes:
            continue  # not reachable within this forecast's horizon

        reposition_cost = distance_km * fuel_cost_per_km
        value = float(forecast.predicted_demand_level) * float(forecast.predicted_avg_check) - reposition_cost
        if value > best_value:
            best_value = value
            best_district_id = district_id
            best_forecast = forecast

    action, expected_uplift_pct = _resolve_move(
        current_value, best_value, best_district_id != current_district_id
    )
    if action == "stay":
        best_district_id, best_forecast = current_district_id, current_forecast

    # NOTE: `probability` is a demand-level PROXY, not a calibrated order
    # probability. demand_level (0–1) stands in for confidence because we don't
    # yet track per-forecast residual history. UIs must label it "уровень
    # спроса", never «вероятность заказа» — see the schema/render docstrings.
    probability = float(best_forecast.predicted_demand_level) if best_forecast else 0.5

    rec = Recommendation(
        user_id=user_id,
        current_district_id=current_district_id,
        recommended_district_id=best_district_id,
        recommended_horizon_minutes=horizon_minutes,
        action=action,
        probability=round(min(0.97, max(0.05, probability)), 3),
        expected_avg_check=float(best_forecast.predicted_avg_check) if best_forecast else 0.0,
        rationale_text=_build_rationale(current, districts[best_district_id], best_forecast, action, session),
        delivered_via="web",
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    # Derived response-only fields (not persisted columns): the income uplift we
    # already computed above, and how long this answer stays valid. Attached to
    # the ORM instance so RecommendationOut (from_attributes) can read them.
    rec.expected_uplift_pct = expected_uplift_pct
    rec.valid_until = _valid_until(best_forecast)
    return rec
