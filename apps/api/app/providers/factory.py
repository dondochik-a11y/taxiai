"""Resolves each provider Protocol to a concrete mock/live implementation based
on PROVIDER_MODE + per-provider overrides (see app/core/config.py). Routers and
services should only ever depend on these functions via FastAPI Depends(),
never import a concrete provider class directly.

Note: MapsProvider has no live/ counterpart — geocode() is PostGIS
point-in-polygon math against our own districts table, not a network call, so
mock/maps_mock.py IS the permanent implementation regardless of mode. A live
routing provider (drive-time/ETA) would be added here if/when a Yandex Maps
key and a routing feature are introduced.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.providers.base import (
    CalendarProvider,
    FlightsProvider,
    LLMProvider,
    MapsProvider,
    MetroProvider,
    PricingProvider,
    TrafficProvider,
    WeatherProvider,
)
from app.providers.mock.calendar_mock import MockCalendarProvider
from app.providers.mock.flights_mock import MockFlightsProvider
from app.providers.mock.llm_mock import MockLLMProvider
from app.providers.mock.maps_mock import MockMapsProvider
from app.providers.mock.metro_mock import MockMetroProvider
from app.providers.mock.traffic_mock import MockTrafficProvider
from app.providers.mock.weather_mock import MockWeatherProvider


def get_maps_provider(db: Session = Depends(get_db)) -> MapsProvider:
    return MockMapsProvider(db)


def get_llm_provider() -> LLMProvider:
    settings = get_settings()
    mode = settings.resolved_mode(settings.openai_provider_mode, settings.openai_api_key)
    if mode == "live":
        from app.providers.live.llm_openai import OpenAILLMProvider

        return OpenAILLMProvider()
    return MockLLMProvider()


def get_weather_provider(db: Session = Depends(get_db)) -> WeatherProvider:
    settings = get_settings()
    mode = settings.resolved_mode(settings.weather_provider_mode, settings.openweather_api_key)
    if mode == "live":
        from app.providers.live.weather_openweather import OpenWeatherProvider

        return OpenWeatherProvider()
    return MockWeatherProvider(db)


def get_flights_provider(db: Session = Depends(get_db)) -> FlightsProvider:
    settings = get_settings()
    mode = settings.resolved_mode(settings.flights_provider_mode, settings.aviationstack_api_key)
    if mode == "live":
        from app.providers.live.flights_aviationstack import AviationStackFlightsProvider

        return AviationStackFlightsProvider()
    return MockFlightsProvider(db)


def get_metro_provider(db: Session = Depends(get_db)) -> MetroProvider:
    # No known public metro-incidents API for Moscow at MVP time — mock is
    # permanent here too until a real source is identified.
    return MockMetroProvider(db)


def get_traffic_provider(db: Session = Depends(get_db)) -> TrafficProvider:
    settings = get_settings()
    mode = settings.resolved_mode(settings.traffic_provider_mode, settings.tomtom_api_key)
    if mode == "live":
        from app.providers.live.traffic_tomtom import TomTomTrafficProvider

        return TomTomTrafficProvider()
    return MockTrafficProvider(db)


def get_pricing_provider(db: Session = Depends(get_db)) -> PricingProvider:
    settings = get_settings()
    # Both credentials are required for the widget API; gate on either being
    # empty so a half-filled .env degrades to mock instead of erroring.
    key = settings.yandex_taxi_api_key if settings.yandex_taxi_clid else ""
    mode = settings.resolved_mode(settings.pricing_provider_mode, key)
    if mode == "live":
        from app.providers.live.pricing_yandex import YandexPricingProvider

        return YandexPricingProvider()
    from app.providers.mock.pricing_mock import MockPricingProvider

    return MockPricingProvider(db)


def get_calendar_provider() -> CalendarProvider:
    settings = get_settings()
    mode = settings.resolved_mode_keyless(settings.calendar_provider_mode)
    if mode == "live":
        from app.providers.live.calendar_isdayoff import IsDayOffCalendarProvider

        return IsDayOffCalendarProvider()
    return MockCalendarProvider()
