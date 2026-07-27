"""Pure, DB-free normalisation + validation for manually-entered trips and
expenses (office task #101, the real-data loop). Kept free of SQLAlchemy so the
rules (what's a valid amount, how to fill the fields the daily summary needs
from a minimal quick-log) are directly unit-testable. The routers do the DB
work; this module only shapes and checks the input.
"""
from __future__ import annotations

from datetime import datetime, timedelta

# A manual quick-log only asks for the money and the distance; every other
# column the Trip model requires (coordinates, pickup/wait times) is irrelevant
# to the daily summary, so we fill it with a harmless zero rather than nag the
# driver for it.
_DEFAULT_TARIFF = "economy"


def validate_trip_amount(price: float | None, distance_km: float | None) -> None:
    """Reject a manual trip whose money/distance make no sense. Raises
    ValueError with a Russian message the API surfaces as a 422 detail."""
    if price is None or price <= 0:
        raise ValueError("Сумма поездки должна быть больше 0.")
    if distance_km is None or distance_km < 0:
        raise ValueError("Расстояние не может быть отрицательным.")


def normalize_manual_trip(
    payload: dict, *, now: datetime, default_district_id: int | None
) -> dict:
    """Turn a minimal quick-log payload (price + distance, everything else
    optional) into the full set of Trip column values, filling sane defaults so
    the row satisfies the model's NOT NULL columns and lands in
    compute_daily_summary exactly like a synthetic trip.

    * start_time defaults to `now`; end_time to start+duration (or start when no
      duration); duration is recovered from the timestamps when omitted.
    * districts fall back to `default_district_id` (the driver's home district,
      resolved by the caller) so the trip's AI post-mortem still has a district.
    * coordinates / pickup / wait default to 0 — unused by the daily summary.

    Raises ValueError (via validate_trip_amount) on nonsensical money/distance.
    """
    price = payload.get("price")
    distance_km = payload.get("distance_km")
    validate_trip_amount(price, distance_km)

    start_time = payload.get("start_time") or now
    duration_seconds = payload.get("duration_seconds")
    end_time = payload.get("end_time")
    if end_time is None:
        end_time = (
            start_time + timedelta(seconds=duration_seconds)
            if duration_seconds
            else start_time
        )
    if duration_seconds is None:
        duration_seconds = max(int((end_time - start_time).total_seconds()), 0)

    start_district_id = payload.get("start_district_id") or default_district_id
    end_district_id = payload.get("end_district_id") or start_district_id

    def _coord(key: str) -> float:
        value = payload.get(key)
        return float(value) if value is not None else 0.0

    return {
        "start_time": start_time,
        "end_time": end_time,
        "start_district_id": start_district_id,
        "end_district_id": end_district_id,
        "start_lat": _coord("start_lat"),
        "start_lng": _coord("start_lng"),
        "end_lat": _coord("end_lat"),
        "end_lng": _coord("end_lng"),
        "time_to_pickup_seconds": int(payload.get("time_to_pickup_seconds") or 0),
        "wait_time_seconds": int(payload.get("wait_time_seconds") or 0),
        "distance_km": float(distance_km),
        "duration_seconds": int(duration_seconds),
        "price": float(price),
        "tariff": payload.get("tariff") or _DEFAULT_TARIFF,
        "surge_multiplier_at_start": payload.get("surge_multiplier_at_start"),
    }


def validate_expense_amount(amount: float | None) -> None:
    """A logged expense must be a positive amount. Raises ValueError (→ 422)."""
    if amount is None or amount <= 0:
        raise ValueError("Сумма расхода должна быть больше 0.")
