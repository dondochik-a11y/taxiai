"""Real OpenWeather current-conditions call. Selected automatically once
OPENWEATHER_API_KEY is set (see app/providers/factory.py).
"""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.core.config import get_settings

_URL = "https://api.openweathermap.org/data/2.5/weather"


class OpenWeatherProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_current(self, district_id: int | None = None) -> dict:
        resp = httpx.get(
            _URL,
            params={"q": "Moscow,RU", "appid": self.settings.openweather_api_key, "units": "metric"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        condition = (data.get("weather") or [{}])[0].get("main", "").lower()
        precipitation_type = "none"
        if "snow" in condition:
            precipitation_type = "snow"
        elif "rain" in condition or "drizzle" in condition:
            precipitation_type = "rain"
        return {
            "observed_at": datetime.now(timezone.utc),
            "temperature_c": data.get("main", {}).get("temp"),
            "precipitation_type": precipitation_type,
            "precipitation_mm": data.get("rain", {}).get("1h", 0.0),
            "wind_speed_ms": data.get("wind", {}).get("speed", 0.0),
            "condition_text": condition or "unknown",
        }
