"""Assembles a structured context bundle per trip and passes it to
LLMProvider.analyze_trip() — provider-agnostic; only the final rendering
differs between the mock template engine and (later) real OpenAI.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.ai_analysis import AiTripAnalysis
from app.models.district import District
from app.models.forecast import Forecast
from app.models.pattern_insight import PatternInsight
from app.models.trip import Trip
from app.providers.base import LLMProvider

ROLLING_WINDOW_DAYS = 30


def _rolling_averages(session: Session, user_id: uuid.UUID, before) -> dict:
    since = before - timedelta(days=ROLLING_WINDOW_DAYS)
    trips = (
        session.execute(
            select(Trip).where(Trip.user_id == user_id, Trip.start_time >= since, Trip.start_time < before)
        )
        .scalars()
        .all()
    )
    if not trips:
        return {}
    avg_wait = sum(t.wait_time_seconds for t in trips) / len(trips)
    avg_price_per_km = sum(float(t.price) / max(float(t.distance_km), 0.1) for t in trips) / len(trips)
    return {"avg_wait_time_seconds": avg_wait, "avg_price_per_km": avg_price_per_km}


def _best_nearby_district(session: Session, exclude_district_id: int, horizon_minutes: int = 30) -> dict | None:
    rows = (
        session.execute(
            select(Forecast)
            .where(Forecast.horizon_minutes == horizon_minutes, Forecast.district_id != exclude_district_id)
            .order_by(Forecast.generated_at.desc())
        )
        .scalars()
        .all()
    )
    latest_by_district: dict[int, Forecast] = {}
    for f in rows:
        latest_by_district.setdefault(f.district_id, f)
    if not latest_by_district:
        return None
    best = max(latest_by_district.values(), key=lambda f: float(f.predicted_avg_check))
    district = session.get(District, best.district_id)
    return {"district_name": district.name, "expected_avg_check": float(best.predicted_avg_check)}


def _relevant_pattern_insights(session: Session, district_name: str) -> list[dict]:
    rows = session.execute(select(PatternInsight)).scalars().all()
    return [
        {"pattern_text": p.pattern_text}
        for p in rows
        if p.condition_json.get("district") == district_name
    ]


def build_trip_context(session: Session, trip: Trip) -> dict:
    start_district = session.get(District, trip.start_district_id)
    return {
        "trip": {
            "price": float(trip.price),
            "distance_km": float(trip.distance_km),
            "wait_time_seconds": trip.wait_time_seconds,
            "time_to_pickup_seconds": trip.time_to_pickup_seconds,
            "start_district_name": start_district.name,
        },
        "rolling_averages": _rolling_averages(session, trip.user_id, trip.start_time),
        "best_nearby_district": _best_nearby_district(session, trip.start_district_id),
        "pattern_insights": _relevant_pattern_insights(session, start_district.name),
    }


def analyze_trip(session: Session, trip: Trip, llm_provider: LLMProvider) -> AiTripAnalysis:
    existing = session.execute(
        select(AiTripAnalysis).where(AiTripAnalysis.trip_id == trip.id)
    ).scalar_one_or_none()
    if existing:
        return existing

    context = build_trip_context(session, trip)
    result = llm_provider.analyze_trip(context)

    analysis = AiTripAnalysis(
        trip_id=trip.id,
        user_id=trip.user_id,
        summary_text=result["summary_text"],
        estimated_missed_earnings=result.get("estimated_missed_earnings"),
        suggested_action=result.get("suggested_action"),
        model_used=result["model_used"],
    )
    session.add(analysis)
    session.commit()
    session.refresh(analysis)
    return analysis
