"""Poll real Yandex Taxi prices per district (live mode only, no-op otherwise).

For every district, quotes the reference route (centroid pulled 35% toward the
city center — the same deterministic route surge_service uses for its rolling
baseline) and stores one price_observations row. The surge coefficient itself
is never stored: surge_service derives it at read time as price / baseline,
and serves it as the "live" source when radar readings are absent.

Dormant until YANDEX_TAXI_CLID + YANDEX_TAXI_API_KEY are set (the key is
issued on request at https://yandex.ru/dev/taxi/). Request limits are agreed
individually, so the cadence is configurable via PRICING_POLL_MINUTES
(default 30 → 130 districts ≈ 6.2k requests/day; raise the interval if the
agreed limit is lower).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import Base  # noqa: F401  (must import before any single app.models.* submodule)
from app.core.config import get_settings
from app.models.district import District
from app.models.pricing import PriceObservation
from app.services.surge_service import reference_route

logger = logging.getLogger(__name__)

# Yandex asks for individually-negotiated limits; pace requests instead of
# bursting, and stop the sweep entirely if the API keeps failing (wrong key,
# exhausted quota) rather than hammer all 130 districts.
_PAUSE_SECONDS = 0.3
_MAX_CONSECUTIVE_ERRORS = 5


def poll_prices(session: Session) -> int:
    settings = get_settings()
    key = settings.yandex_taxi_api_key if settings.yandex_taxi_clid else ""
    if settings.resolved_mode(settings.pricing_provider_mode, key) != "live":
        return 0

    from app.providers.live.pricing_yandex import YandexPricingProvider

    provider = YandexPricingProvider()
    districts = session.execute(select(District)).scalars().all()

    now = datetime.now(timezone.utc)
    inserted = 0
    consecutive_errors = 0
    for d in districts:
        from_lat, from_lng = float(d.centroid_lat), float(d.centroid_lng)
        to_lat, to_lng = reference_route(from_lat, from_lng)
        try:
            quote = provider.get_ride_price(from_lat, from_lng, to_lat, to_lng)
        except Exception:
            consecutive_errors += 1
            if consecutive_errors >= _MAX_CONSECUTIVE_ERRORS:
                logger.exception(
                    "price poll aborted after %d consecutive failures (%d districts done)",
                    consecutive_errors,
                    inserted,
                )
                break
            continue
        consecutive_errors = 0
        session.add(
            PriceObservation(
                observed_at=now,
                district_id=d.id,
                tariff_class=quote["tariff_class"],
                price=quote["price"],
                currency=quote["currency"],
            )
        )
        inserted += 1
        time.sleep(_PAUSE_SECONDS)

    session.commit()
    return inserted
