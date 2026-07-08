from datetime import date

from app.synth import signal_config as cfg


class MockCalendarProvider:
    """Fixed-date Russian public holidays — the same list the synthetic
    generator already seeds into calendar_events (see synth/signal_config.py),
    kept here too so a direct provider call behaves consistently with mock
    mode's seeded data."""

    def get_public_holidays(self, year: int) -> list[date]:
        return [date(year, month, day) for month, day in cfg.FIXED_RUSSIAN_HOLIDAYS]
