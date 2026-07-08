"""Protocols for every external integration. Routers/services depend only on
these types (via providers/factory.py + FastAPI Depends), never on a concrete
mock/live class — this is what makes swapping to a real API later a config
change instead of a rewrite.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Protocol


class LLMProvider(Protocol):
    def analyze_trip(self, context: dict[str, Any]) -> dict[str, Any]:
        """Returns {"summary_text": str, "estimated_missed_earnings": float | None,
        "suggested_action": str | None, "model_used": str}."""
        ...

    def chat(self, message: str, context: dict[str, Any]) -> str:
        """Returns the assistant's reply text."""
        ...


class MapsProvider(Protocol):
    def geocode(self, lat: float, lng: float) -> int | None:
        """Returns the district_id containing (lat, lng), or None if outside all districts."""
        ...


class WeatherProvider(Protocol):
    def get_current(self, district_id: int | None = None) -> dict[str, Any]:
        """Returns the most recent weather_observations-shaped dict."""
        ...


class FlightsProvider(Protocol):
    def get_upcoming_flights(self, airport_code: str, since: datetime) -> list[dict[str, Any]]:
        ...


class MetroProvider(Protocol):
    def get_active_incidents(self) -> list[dict[str, Any]]:
        ...


class TrafficProvider(Protocol):
    def get_current(self, lat: float, lng: float) -> dict[str, Any]:
        """Returns {"congestion_level": float (0-10), "avg_speed_kmh": float | None}."""
        ...


class CalendarProvider(Protocol):
    def get_public_holidays(self, year: int) -> list[date]:
        ...


class PricingProvider(Protocol):
    def get_ride_price(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> dict[str, Any]:
        """Returns {"price": float, "currency": str, "tariff_class": str} for the
        cheapest quote on the given route right now. The surge coefficient is
        NOT part of this contract — no public aggregator exposes it directly;
        it is derived downstream as price / rolling per-district baseline."""
        ...
