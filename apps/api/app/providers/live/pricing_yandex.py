"""Real Yandex Taxi widget API ("API Такси: информация о стоимости поездки").
Selected automatically once YANDEX_TAXI_CLID + YANDEX_TAXI_API_KEY are set
(see app/providers/factory.py). The key is issued on request at
https://yandex.ru/dev/taxi/ — request limits are agreed individually, which is
why the poll cadence is configurable (PRICING_POLL_MINUTES, default 30).

The API returns the current *price* for a route, not the surge coefficient —
Yandex does not expose surge publicly. The coefficient is reconstructed in
app/services/surge_service.py as price / rolling per-district baseline.
"""
from __future__ import annotations

from typing import Any

import httpx

from app.core.config import get_settings

_URL = "https://taxi-routeinfo.taxi.yandex.net/taxi_info"


class YandexPricingProvider:
    def __init__(self) -> None:
        self.settings = get_settings()

    def get_ride_price(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> dict[str, Any]:
        resp = httpx.get(
            _URL,
            params={
                "clid": self.settings.yandex_taxi_clid,
                "apikey": self.settings.yandex_taxi_api_key,
                # rll is lng,lat pairs (Yandex order), "~"-separated.
                "rll": f"{from_lng},{from_lat}~{to_lng},{to_lat}",
                "class": "econom",
            },
            headers={"Accept": "application/json"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        option = data["options"][0]
        return {
            "price": float(option["price"]),
            "currency": data.get("currency", "RUB"),
            "tariff_class": option.get("class_name", "econom"),
        }
