"""Daily sync of real public holidays via the calendar provider (isDayOff.ru
in live mode — free, no key required, see
app/providers/live/calendar_isdayoff.py). In mock mode this is a no-op: the
synthetic generator already seeded holidays at backfill time from the same
hardcoded list app/providers/mock/calendar_mock.py returns, so there's nothing
new to sync.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401  (must import before any single app.models.* submodule)
from app.core.config import get_settings
from app.models.calendar import CalendarEvent
from app.providers.factory import get_calendar_provider


def sync_holidays(session: Session) -> int:
    settings = get_settings()
    if settings.resolved_mode_keyless(settings.calendar_provider_mode) != "live":
        return 0

    provider = get_calendar_provider()
    today = date.today()
    inserted = 0
    for year in (today.year, today.year + 1):
        for day in provider.get_public_holidays(year):
            exists = session.execute(
                select(CalendarEvent).where(
                    CalendarEvent.event_date == day,
                    CalendarEvent.event_type == "public_holiday",
                )
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(
                CalendarEvent(
                    event_date=day,
                    event_type="public_holiday",
                    title="Public holiday (isDayOff.ru)",
                    district_id=None,
                    expected_impact="medium",
                    source="live",
                )
            )
            inserted += 1
    session.commit()
    return inserted


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        n = sync_holidays(db)
        print(f"Synced {n} new holiday rows.")
    finally:
        db.close()
