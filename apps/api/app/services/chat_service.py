"""Free-text AI chat assistant. Assembles a small structured context bundle
(today's finance, rolling averages, latest recommendation, a "where am I
losing money" note) and passes it to LLMProvider.chat() — no vector DB/RAG
needed at this scale, the bundle is small enough to inline directly.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import ChatMessage
from app.models.district import District
from app.models.finance import FinanceSummary
from app.models.recommendation import Recommendation
from app.models.trip import Trip
from app.models.user import DriverProfile
from app.providers.base import LLMProvider
from app.providers.mock.maps_mock import MockMapsProvider
from app.services.finance_service import compute_daily_summary
from app.services.recommendation_service import generate_recommendation

ROLLING_WINDOW_DAYS = 14
CHAT_HISTORY_LIMIT = 20
# A recommendation older than this no longer reflects "now" — regenerate.
RECOMMENDATION_FRESH_MINUTES = 20


def _rolling_averages(session: Session, user_id: uuid.UUID) -> dict:
    since = date.today() - timedelta(days=ROLLING_WINDOW_DAYS)
    rows = (
        session.execute(
            select(FinanceSummary).where(
                FinanceSummary.user_id == user_id, FinanceSummary.summary_date >= since
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return {}
    return {"avg_daily_gross_income": sum(float(r.gross_income) for r in rows) / len(rows)}


def _rec_to_dict(session: Session, rec: Recommendation) -> dict:
    district = session.get(District, rec.recommended_district_id)
    return {
        "recommended_district_name": district.name,
        "probability": float(rec.probability),
        "expected_avg_check": float(rec.expected_avg_check),
        "horizon_minutes": rec.recommended_horizon_minutes,
    }


def _ensure_recommendation(session: Session, user_id: uuid.UUID) -> dict | None:
    """Latest recommendation for the user, regenerated from their home district
    if none exists yet or the last one is stale. In Telegram the bot has no live
    location, so the home district's centroid is the origin — this is what makes
    'куда ехать?' answerable in the chat/bot at all (the web flow seeds a
    recommendation from real geolocation, but a bot-first user never triggers
    that)."""
    rec = session.execute(
        select(Recommendation)
        .where(Recommendation.user_id == user_id)
        .order_by(Recommendation.generated_at.desc())
    ).scalars().first()

    if rec is not None:
        generated = rec.generated_at
        if generated.tzinfo is None:
            generated = generated.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - generated < timedelta(minutes=RECOMMENDATION_FRESH_MINUTES):
            return _rec_to_dict(session, rec)

    profile = session.execute(
        select(DriverProfile).where(DriverProfile.user_id == user_id)
    ).scalar_one_or_none()
    if profile and profile.home_district_id is not None:
        home = session.get(District, profile.home_district_id)
        if home is not None:
            try:
                fresh = generate_recommendation(
                    session, user_id, float(home.centroid_lat), float(home.centroid_lng),
                    MockMapsProvider(session), horizon_minutes=30,
                )
                return _rec_to_dict(session, fresh)
            except ValueError:
                pass

    return _rec_to_dict(session, rec) if rec is not None else None


def _worst_district_note(session: Session, user_id: uuid.UUID) -> str | None:
    since = date.today() - timedelta(days=ROLLING_WINDOW_DAYS)
    trips = (
        session.execute(select(Trip).where(Trip.user_id == user_id, Trip.start_time >= since))
        .scalars()
        .all()
    )
    if len(trips) < 5:
        return None

    by_district: dict[int, list[Trip]] = {}
    for t in trips:
        by_district.setdefault(t.start_district_id, []).append(t)

    def _income_per_hour(group: list[Trip]) -> float:
        total_price = sum(float(t.price) for t in group)
        total_hours = sum(t.duration_seconds for t in group) / 3600
        return total_price / total_hours if total_hours > 0 else 0.0

    ranked = sorted(by_district.items(), key=lambda kv: _income_per_hour(kv[1]))
    if not ranked:
        return None
    worst_district_id, worst_trips = ranked[0]
    district = session.get(District, worst_district_id)
    return (
        f"Меньше всего вы зарабатываете в час в районе «{district.name}» "
        f"(≈{_income_per_hour(worst_trips):.0f} ₽/ч за последние {ROLLING_WINDOW_DAYS} дней)."
    )


def build_chat_context(session: Session, user_id: uuid.UUID) -> dict:
    today_summary = compute_daily_summary(session, user_id, date.today())
    return {
        "today_finance": {"gross_income": float(today_summary.gross_income)},
        "rolling_averages": _rolling_averages(session, user_id),
        "latest_recommendation": _ensure_recommendation(session, user_id),
        "worst_district_note": _worst_district_note(session, user_id),
    }


def send_message(session: Session, user_id: uuid.UUID, message: str, llm_provider: LLMProvider) -> str:
    session.add(ChatMessage(user_id=user_id, role="user", content=message))

    context = build_chat_context(session, user_id)
    reply = llm_provider.chat(message, context)

    session.add(ChatMessage(user_id=user_id, role="assistant", content=reply))
    session.commit()
    return reply


def get_history(session: Session, user_id: uuid.UUID, limit: int = CHAT_HISTORY_LIMIT) -> list[ChatMessage]:
    rows = (
        session.execute(
            select(ChatMessage)
            .where(ChatMessage.user_id == user_id)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return list(reversed(rows))
