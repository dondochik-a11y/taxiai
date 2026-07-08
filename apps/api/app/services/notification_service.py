"""Decides which Telegram notifications are due right now, for every linked
driver, and logs an at-most-once dedup row per (user, type, date) — see
app/models/notification.py for why that's an acceptable MVP simplification.
All decisioning happens here, server-side; the bot itself is a thin adapter
that polls GET /v1/telegram/pending-notifications and just renders + sends
whatever this returns (see app/services/*, apps/bot/bot/scheduler.py).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.district import District
from app.models.enums import NotificationType
from app.models.forecast import Forecast
from app.models.notification import TelegramNotificationLog
from app.models.trip import Trip
from app.models.user import DriverProfile, User
from app.services.daily_plan_service import get_daily_plan
from app.services.finance_service import compute_daily_summary

HIGH_DEMAND_THRESHOLD = 0.65
_WEEKDAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _already_sent(session: Session, user_id, notif_type: NotificationType, today: date) -> bool:
    return (
        session.execute(
            select(TelegramNotificationLog).where(
                TelegramNotificationLog.user_id == user_id,
                TelegramNotificationLog.notification_type == notif_type,
                TelegramNotificationLog.notification_date == today,
            )
        ).scalar_one_or_none()
        is not None
    )


def _mark_sent(session: Session, user_id, notif_type: NotificationType, today: date) -> None:
    session.add(
        TelegramNotificationLog(user_id=user_id, notification_type=notif_type, notification_date=today)
    )


def _schedule_hour(work_schedule: dict, weekday: int, edge: str) -> int | None:
    """edge is 'start' or 'end'. work_schedule looks like {"mon": ["08:00-20:00"]}."""
    ranges = work_schedule.get(_WEEKDAY_KEYS[weekday]) or []
    if not ranges:
        return None
    start_str, end_str = ranges[0].split("-")
    return int((start_str if edge == "start" else end_str).split(":")[0])


def _morning_plan_notification(session: Session, user: User, profile: DriverProfile, now: datetime, today: date) -> dict | None:
    if _already_sent(session, user.id, NotificationType.MORNING_PLAN, today):
        return None
    start_hour = _schedule_hour(profile.work_schedule or {}, today.weekday(), "start")
    if start_hour is None or not (start_hour - 1 <= now.hour <= start_hour):
        return None
    windows = get_daily_plan(session, today.weekday())
    if not windows:
        return None
    _mark_sent(session, user.id, NotificationType.MORNING_PLAN, today)
    windows_text = ", ".join(f"{w['start_hour']:02d}:00–{w['end_hour']:02d}:00" for w in windows)
    return {
        "type": NotificationType.MORNING_PLAN.value,
        "user_id": str(user.id),
        "telegram_id": user.telegram_id,
        "text": f"Сегодня рекомендуем работать:\n{windows_text}",
    }


def _preshift_alert_notification(session: Session, user: User, profile: DriverProfile, now: datetime, today: date) -> dict | None:
    if profile.home_district_id is None or _already_sent(session, user.id, NotificationType.PRESHIFT_ALERT, today):
        return None
    forecast = (
        session.execute(
            select(Forecast)
            .where(Forecast.district_id == profile.home_district_id, Forecast.horizon_minutes == 30)
            .order_by(Forecast.generated_at.desc())
        )
        .scalars()
        .first()
    )
    if forecast is None or float(forecast.predicted_demand_level) < HIGH_DEMAND_THRESHOLD:
        return None
    district = session.get(District, profile.home_district_id)
    _mark_sent(session, user.id, NotificationType.PRESHIFT_ALERT, today)
    return {
        "type": NotificationType.PRESHIFT_ALERT.value,
        "user_id": str(user.id),
        "telegram_id": user.telegram_id,
        "text": (
            f"Через {forecast.horizon_minutes} минут ожидается высокий спрос "
            f"в районе «{district.name}» (вероятность {float(forecast.predicted_demand_level) * 100:.0f}%)."
        ),
    }


def _postshift_summary_notification(session: Session, user: User, profile: DriverProfile, now: datetime, today: date) -> dict | None:
    if _already_sent(session, user.id, NotificationType.POSTSHIFT_SUMMARY, today):
        return None
    end_hour = _schedule_hour(profile.work_schedule or {}, today.weekday(), "end")
    if end_hour is None or now.hour < end_hour:
        return None

    trips_today = (
        session.execute(
            select(Trip).where(
                Trip.user_id == user.id,
                Trip.start_time >= datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc),
            )
        )
        .scalars()
        .all()
    )
    if not trips_today:
        return None

    summary = compute_daily_summary(session, user.id, today)

    by_district: dict[int, list[Trip]] = {}
    for t in trips_today:
        by_district.setdefault(t.start_district_id, []).append(t)
    ranked = sorted(
        by_district.items(), key=lambda kv: sum(float(t.price) for t in kv[1]) / len(kv[1]), reverse=True
    )
    best_name = session.get(District, ranked[0][0]).name if ranked else "—"
    worst_name = session.get(District, ranked[-1][0]).name if ranked else "—"

    _mark_sent(session, user.id, NotificationType.POSTSHIFT_SUMMARY, today)
    return {
        "type": NotificationType.POSTSHIFT_SUMMARY.value,
        "user_id": str(user.id),
        "telegram_id": user.telegram_id,
        "text": (
            f"Сегодня\nДоход: {summary.gross_income:.0f}\nЧистыми: {summary.net_income:.0f}\n"
            f"Лучший район: {best_name}\nХудший район: {worst_name}"
        ),
    }


def get_pending_notifications(session: Session) -> list[dict]:
    now = datetime.now(timezone.utc)
    today = now.date()

    rows = (
        session.execute(
            select(User, DriverProfile)
            .join(DriverProfile, DriverProfile.user_id == User.id)
            .where(User.telegram_id.isnot(None))
        )
        .all()
    )

    notifications: list[dict] = []
    for user, profile in rows:
        for builder in (_morning_plan_notification, _preshift_alert_notification, _postshift_summary_notification):
            notif = builder(session, user, profile, now, today)
            if notif:
                notifications.append(notif)

    session.commit()
    return notifications
