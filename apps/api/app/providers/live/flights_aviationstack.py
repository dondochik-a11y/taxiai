"""Real AviationStack flights call. Selected automatically once
AVIATIONSTACK_API_KEY is set (see app/providers/factory.py).
"""
from __future__ import annotations

from datetime import datetime

import httpx

from app.core.config import get_settings

_URL = "http://api.aviationstack.com/v1/flights"

# AviationStack's flight_status is {scheduled, active, landed, cancelled,
# incident, diverted} — our own schema's FlightStatus enum (see
# app/models/enums.py) only has {on_time, delayed, cancelled, landed}, so
# these must be mapped, not passed through directly (a raw "active" would
# fail the Postgres enum constraint on insert). A non-null `delay` from
# AviationStack takes priority over the raw status either way, since that's
# literally what our "delayed" state means.
_STATUS_MAP = {
    "scheduled": "on_time",
    "active": "on_time",
    "landed": "landed",
    "cancelled": "cancelled",
    "incident": "cancelled",
    "diverted": "cancelled",
}


def _map_status(raw_status: str | None, delay_minutes: int | None) -> str:
    if delay_minutes:
        return "delayed"
    return _STATUS_MAP.get(raw_status or "", "on_time")


class AviationStackFlightsProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_upcoming_flights(self, airport_code: str, since: datetime) -> list[dict]:
        resp = httpx.get(
            _URL,
            params={"access_key": self.settings.aviationstack_api_key, "arr_iata": airport_code},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        rows = []
        for f in data:
            arrival = f.get("arrival", {})
            delay_minutes = arrival.get("delay")
            rows.append(
                {
                    "scheduled_time": arrival.get("scheduled"),
                    "actual_time": arrival.get("actual"),
                    "direction": "arrival",
                    "status": _map_status(f.get("flight_status"), delay_minutes),
                    "delay_minutes": delay_minutes,
                }
            )
        return rows
