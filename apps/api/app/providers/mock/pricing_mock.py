"""Mock pricing: derives a plausible ride price from the latest synthetic
demand snapshot of the district nearest to the pickup point, using the same
base-fare arithmetic as the trip generator. Exists so the pricing pipeline is
exercisable end-to-end without a Yandex key; /v1/surge/current does NOT need
it in mock mode (it falls back to demand_snapshots.surge_multiplier directly).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.demand import DemandSnapshot
from app.models.district import District

# Matches the reference-route economics in app/synth/generator.py: base fare
# plus ~4km / ~12min of ride.
_REFERENCE_NO_SURGE_PRICE = 150.0 + 4 * 22.0 + 12 * 8.0


class MockPricingProvider:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_ride_price(
        self, from_lat: float, from_lng: float, to_lat: float, to_lng: float
    ) -> dict[str, Any]:
        district_id = self.db.execute(
            select(District.id).order_by(
                (District.centroid_lat - from_lat) * (District.centroid_lat - from_lat)
                + (District.centroid_lng - from_lng) * (District.centroid_lng - from_lng)
            ).limit(1)
        ).scalar_one_or_none()
        surge = 1.0
        if district_id is not None:
            latest = self.db.execute(
                select(DemandSnapshot.surge_multiplier)
                .where(DemandSnapshot.district_id == district_id)
                .order_by(DemandSnapshot.observed_at.desc())
                .limit(1)
            ).scalar_one_or_none()
            if latest is not None:
                surge = float(latest)
        return {
            "price": round(_REFERENCE_NO_SURGE_PRICE * surge, 2),
            "currency": "RUB",
            "tariff_class": "econom",
        }
