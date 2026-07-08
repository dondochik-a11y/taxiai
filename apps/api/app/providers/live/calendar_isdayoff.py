"""isDayOff.ru — free Russian production calendar (public holidays / non-working
days), no API key required at all. Genuinely free, so this can safely be set
to live mode with zero cost — see CALENDAR_PROVIDER_MODE in .env.example.
"""
from __future__ import annotations

from datetime import date

import httpx

_URL_TEMPLATE = "https://isdayoff.ru/api/getdata?year={year}&cc=ru"


class IsDayOffCalendarProvider:
    def get_public_holidays(self, year: int) -> list[date]:
        resp = httpx.get(_URL_TEMPLATE.format(year=year), timeout=10.0)
        resp.raise_for_status()
        # Response is a bare string of digits, one per day of the year:
        # 0 = working day, 1 = non-working day, 2 = shortened pre-holiday day.
        # "1" covers every ordinary Saturday/Sunday too, not just holidays —
        # our schema already has a separate synthetic `weekend` event_type, so
        # keep only weekday non-working days here to avoid double-counting a
        # plain Sunday as both "weekend" and "public_holiday".
        days = resp.text.strip()
        holidays: list[date] = []
        current = date(year, 1, 1)
        for i, flag in enumerate(days):
            if flag != "1":
                continue
            day = date.fromordinal(current.toordinal() + i)
            if day.weekday() < 5:
                holidays.append(day)
        return holidays
