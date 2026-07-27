"""Decides which Telegram notifications are due right now, for every linked
driver, and logs an at-most-once dedup row per (user, type, date) — see
app/models/notification.py for why that's an acceptable MVP simplification.
All decisioning happens here, server-side; the bot itself is a thin adapter
that polls GET /v1/telegram/pending-notifications and just renders + sends
whatever this returns (see app/services/*, apps/bot/bot/scheduler.py).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.district import District
from app.models.enums import NotificationType
from app.models.notification import TelegramNotificationLog
from app.models.proximity_alert import ProximitySurgeAlertLog
from app.models.trip import Trip
from app.models.user import DriverProfile, User
from app.services import alerts
from app.services.daily_plan_service import get_daily_plan
from app.services.finance_service import compute_daily_summary
from app.services.surge_service import get_current_surge

# Alert the driver to go out only on a REAL radar kef at least this high — the
# whole point is real data, so a synthetic number never triggers this.
PRESHIFT_KEF_THRESHOLD = 1.5
# Sources from surge_service that carry a real radar reading (see the cascade
# in app/services/surge_service.py); live/synthetic are never alert-worthy here.
_PRESHIFT_REAL_SOURCES = frozenset({"radar", "radar_stale", "radar_near"})
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
        "district_id": None,
        "text": f"Сегодня рекомендуем работать:\n{windows_text}",
    }


def _preshift_alert_notification(session: Session, user: User, profile: DriverProfile, now: datetime, today: date) -> dict | None:
    if profile.home_district_id is None or _already_sent(session, user.id, NotificationType.PRESHIFT_ALERT, today):
        return None
    # Alert on the real radar kef for the home district, never on synthetic.
    home_row = next(
        (r for r in get_current_surge(session) if r["district_id"] == profile.home_district_id),
        None,
    )
    if (
        home_row is None
        or home_row["source"] not in _PRESHIFT_REAL_SOURCES
        or float(home_row["surge"]) < PRESHIFT_KEF_THRESHOLD
    ):
        return None
    district = session.get(District, profile.home_district_id)
    surge = float(home_row["surge"])
    _mark_sent(session, user.id, NotificationType.PRESHIFT_ALERT, today)
    return {
        "type": NotificationType.PRESHIFT_ALERT.value,
        "user_id": str(user.id),
        "telegram_id": user.telegram_id,
        "district_id": profile.home_district_id,
        "text": (
            f"Сейчас в районе «{district.name}» высокий кэф — {surge:.1f}. "
            f"Хорошее время выйти на смену."
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
    best_district_id = ranked[0][0] if ranked else None
    best_name = session.get(District, best_district_id).name if best_district_id is not None else "—"
    worst_name = session.get(District, ranked[-1][0]).name if ranked else "—"

    _mark_sent(session, user.id, NotificationType.POSTSHIFT_SUMMARY, today)
    return {
        "type": NotificationType.POSTSHIFT_SUMMARY.value,
        "user_id": str(user.id),
        "telegram_id": user.telegram_id,
        "district_id": best_district_id,
        "text": (
            f"Сегодня\nДоход: {summary.gross_income:.0f}\nЧистыми: {summary.net_income:.0f}\n"
            f"Лучший район: {best_name}\nХудший район: {worst_name}"
        ),
    }


def _recent_proximity_sends(session: Session, user_id, now: datetime) -> dict[int, datetime]:
    """Latest proximity-alert timestamp per district for this driver within the
    cooldown horizon — feeds alerts.select_surge_alerts' cooldown gate."""
    since = now - alerts.PROXIMITY_COOLDOWN
    rows = session.execute(
        select(ProximitySurgeAlertLog.district_id, func.max(ProximitySurgeAlertLog.sent_at))
        .where(
            ProximitySurgeAlertLog.user_id == user_id,
            ProximitySurgeAlertLog.sent_at >= since,
        )
        .group_by(ProximitySurgeAlertLog.district_id)
    ).all()
    return {district_id: sent_at for district_id, sent_at in rows}


def _proximity_surge_notifications(
    session: Session, rows: list, now: datetime
) -> list[dict]:
    """Proactive «рядом скачок спроса»: for each opted-in driver on shift, push
    when a nearby district's CURRENT real kef is at/above their threshold.

    "Nearby" is the home district + its nearest neighbours by centroid distance
    (alerts.nearby_district_ids) — Telegram gives us no passive live GPS, so we
    anchor on the known home district, not a live position. Throttled per
    (driver, district) via proximity_surge_alert_log, distinct from the once/day
    PRESHIFT dedup. Unlike the single-shot builders above, one driver can yield
    several alerts in a tick (several nearby districts surging)."""
    active = [
        (user, profile)
        for user, profile in rows
        if profile.surge_alert_enabled
        and profile.home_district_id is not None
        and alerts.is_within_shift(profile.work_schedule or {}, now.weekday(), now.hour)
    ]
    if not active:
        return []

    surge_by_district = {r["district_id"]: r for r in get_current_surge(session)}
    centroids = {
        district_id: (float(lat), float(lng))
        for district_id, lat, lng in session.execute(
            select(District.id, District.centroid_lat, District.centroid_lng)
        ).all()
    }

    notifications: list[dict] = []
    for user, profile in active:
        nearby = alerts.nearby_district_ids(profile.home_district_id, centroids)
        threshold = float(profile.surge_alert_threshold or alerts.DEFAULT_SURGE_THRESHOLD)
        last_sent = _recent_proximity_sends(session, user.id, now)
        due_ids = alerts.select_surge_alerts(nearby, surge_by_district, threshold, last_sent, now)
        if not due_ids:
            continue
        home_lat, home_lng = centroids[profile.home_district_id]
        for district_id in due_ids:
            row = surge_by_district[district_id]
            district = session.get(District, district_id)
            surge = float(row["surge"])
            if district_id == profile.home_district_id:
                hint = ""
            else:
                d_lat, d_lng = centroids[district_id]
                dist = alerts.distance_km(home_lat, home_lng, d_lat, d_lng)
                direction = alerts.direction_hint(home_lat, home_lng, d_lat, d_lng)
                hint = f" (~{dist:.0f} км{' ' + direction if direction else ''})"
            notifications.append(
                {
                    "type": alerts.PROXIMITY_SURGE_TYPE,
                    "user_id": str(user.id),
                    "telegram_id": user.telegram_id,
                    "district_id": district_id,
                    "text": (
                        f"🚀 Рядом скачок спроса!\n"
                        f"В районе «{district.name}» сейчас кэф {surge:.1f}{hint}. "
                        f"Успей заехать."
                    ),
                }
            )
            session.add(
                ProximitySurgeAlertLog(user_id=user.id, district_id=district_id, sent_at=now)
            )
    return notifications


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

    notifications.extend(_proximity_surge_notifications(session, rows, now))

    session.commit()
    return notifications
