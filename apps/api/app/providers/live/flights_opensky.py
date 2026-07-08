"""Real-time aircraft detection via OpenSky Network's OAuth2 client-credentials
API — a genuinely different data shape than AviationStack's flight schedules:
live ADS-B state vectors (position/altitude/vertical-rate), not scheduled
times. Used to detect "a plane is actually landing near this airport right
now" on a short interval, feeding the same arrival-density signal the demand
generator already reads from airport_flights (see
app/synth/generator.py::_arrival_density_boost) — complementary to, not a
replacement for, the daily AviationStack schedule sync in
app/providers/live/flights_aviationstack.py.
"""
from __future__ import annotations

import time

import httpx

from app.core.config import get_settings

_TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"
_STATES_URL = "https://opensky-network.org/api/states/all"

_BBOX_DEGREES = 0.15  # ~15km catchment radius around each airport centroid
_LOW_ALTITUDE_M = 1000

# Module-level so the short-lived (~30 min) OAuth2 token is reused across
# calls within a process instead of re-authenticating every tick.
_token_cache: dict = {}


def _get_access_token(client_id: str, client_secret: str) -> str:
    cached = _token_cache.get("token")
    if cached and _token_cache.get("expires_at", 0) > time.time() + 30:
        return cached
    resp = httpx.post(
        _TOKEN_URL,
        data={"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret},
        timeout=10.0,
    )
    resp.raise_for_status()
    data = resp.json()
    _token_cache["token"] = data["access_token"]
    _token_cache["expires_at"] = time.time() + data.get("expires_in", 1800)
    return data["access_token"]


class OpenSkyArrivalDetector:
    def __init__(self) -> None:
        self.settings = get_settings()

    def count_arrivals_near(self, lat: float, lng: float) -> int:
        """Counts aircraft near (lat, lng) that look like they're landing or
        have just landed: on the ground, or low altitude and descending."""
        token = _get_access_token(self.settings.opensky_client_id, self.settings.opensky_client_secret)
        params = {
            "lamin": lat - _BBOX_DEGREES,
            "lamax": lat + _BBOX_DEGREES,
            "lomin": lng - _BBOX_DEGREES,
            "lomax": lng + _BBOX_DEGREES,
        }
        resp = httpx.get(_STATES_URL, params=params, headers={"Authorization": f"Bearer {token}"}, timeout=15.0)
        resp.raise_for_status()
        states = resp.json().get("states") or []

        count = 0
        for s in states:
            # Fixed positional fields per OpenSky's /states/all schema:
            # index 7 = baro_altitude, 8 = on_ground, 11 = vertical_rate.
            on_ground = s[8]
            baro_altitude = s[7]
            vertical_rate = s[11]
            if on_ground:
                count += 1
            elif (
                baro_altitude is not None
                and baro_altitude < _LOW_ALTITUDE_M
                and vertical_rate is not None
                and vertical_rate < -1
            ):
                count += 1
        return count
