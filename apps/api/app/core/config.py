from functools import lru_cache
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderMode = Literal["mock", "live"]

_PROVIDER_MODE_FIELDS = (
    "openai_provider_mode",
    "maps_provider_mode",
    "weather_provider_mode",
    "flights_provider_mode",
    "metro_provider_mode",
    "traffic_provider_mode",
    "calendar_provider_mode",
    "opensky_provider_mode",
    "pricing_provider_mode",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @field_validator(*_PROVIDER_MODE_FIELDS, mode="before")
    @classmethod
    def _blank_env_value_means_unset(cls, value: object) -> object | None:
        # `.env.example` ships these as `KEY=` (blank) so every integration is
        # optional by default — Pydantic's Literal["mock","live"] | None
        # rejects "" as neither a valid literal nor None, so normalize here.
        if value == "":
            return None
        return value

    environment: str = "development"
    secret_key: str = "change-me"

    database_url: str = "postgresql+psycopg://taxi:taxi@localhost:5432/taxi"
    redis_url: str = "redis://localhost:6379/0"

    # Global default provider mode; per-provider settings below override it when set.
    provider_mode: ProviderMode = "mock"

    openai_provider_mode: ProviderMode | None = None
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    maps_provider_mode: ProviderMode | None = None
    yandex_maps_api_key: str = ""

    weather_provider_mode: ProviderMode | None = None
    openweather_api_key: str = ""

    flights_provider_mode: ProviderMode | None = None
    aviationstack_api_key: str = ""

    metro_provider_mode: ProviderMode | None = None
    metro_api_key: str = ""

    traffic_provider_mode: ProviderMode | None = None
    tomtom_api_key: str = ""

    # isDayOff.ru needs no API key at all — see resolved_mode_keyless below.
    calendar_provider_mode: ProviderMode | None = None

    # OpenSky Network — real-time aircraft positions (OAuth2 client-credentials),
    # complementary to AviationStack's daily schedule sync, not a replacement.
    # See app/providers/live/flights_opensky.py.
    opensky_provider_mode: ProviderMode | None = None
    opensky_client_id: str = ""
    opensky_client_secret: str = ""

    # Yandex Taxi widget API — real ride prices per district, from which the
    # live surge coefficient is derived. Key issued on request
    # (https://yandex.ru/dev/taxi/), limits negotiated individually — hence the
    # configurable poll cadence.
    pricing_provider_mode: ProviderMode | None = None
    yandex_taxi_clid: str = ""
    yandex_taxi_api_key: str = ""
    pricing_poll_minutes: int = 30

    telegram_bot_token: str = ""

    def resolved_mode(self, override: ProviderMode | None, required_key: str) -> ProviderMode:
        """Resolve effective mode for a provider: per-provider override > global default,
        but never 'live' without the key present — falls back to mock instead of crashing."""
        mode = override or self.provider_mode
        if mode == "live" and not required_key:
            return "mock"
        return mode

    def resolved_mode_keyless(self, override: ProviderMode | None) -> ProviderMode:
        """Same resolution as resolved_mode, but for providers with no API key
        at all (isDayOff) — nothing to gate on, live is always safe to use."""
        return override or self.provider_mode


@lru_cache
def get_settings() -> Settings:
    return Settings()
