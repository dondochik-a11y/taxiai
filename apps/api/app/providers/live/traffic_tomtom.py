"""Real TomTom Traffic Flow API call. Selected automatically once
TOMTOM_API_KEY is set (see app/providers/factory.py). Free tier: 2,500
non-tile requests/day — plenty for hourly per-district polling.
"""
from __future__ import annotations

import httpx

from app.core.config import get_settings

_URL = "https://api.tomtom.com/traffic/services/4/flowSegmentData/absolute/10/json"


class TomTomTrafficProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_current(self, lat: float, lng: float) -> dict:
        resp = httpx.get(
            _URL,
            params={"key": self.settings.tomtom_api_key, "point": f"{lat},{lng}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json().get("flowSegmentData", {})
        current_speed = data.get("currentSpeed")
        free_flow_speed = data.get("freeFlowSpeed")
        congestion_level = 0.0
        if current_speed is not None and free_flow_speed:
            # 0 = free-flowing (current == free-flow speed), 10 = gridlock.
            congestion_level = round(max(0.0, min(10.0, (1 - current_speed / free_flow_speed) * 10)), 1)
        return {"congestion_level": congestion_level, "avg_speed_kmh": current_speed}
