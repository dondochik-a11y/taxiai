"""Pure-logic tests for the manual trip/expense intake (office task #101) and
the depreciation formula. DB-free, mirroring test_shift_goal_weekly.py."""
from datetime import datetime, timezone

import pytest

from app.services.finance_service import depreciation_per_km
from app.services.manual_entry import (
    normalize_manual_trip,
    validate_expense_amount,
    validate_trip_amount,
)

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


class TestNormalizeManualTrip:
    def test_minimal_payload_fills_defaults(self):
        fields = normalize_manual_trip(
            {"price": 450, "distance_km": 12}, now=NOW, default_district_id=7
        )
        assert fields["price"] == 450.0
        assert fields["distance_km"] == 12.0
        # No timestamps given → start=now, end=start (zero-length), duration 0.
        assert fields["start_time"] == NOW
        assert fields["end_time"] == NOW
        assert fields["duration_seconds"] == 0
        # Districts fall back to the resolved default; coords/pickup/wait → 0.
        assert fields["start_district_id"] == 7
        assert fields["end_district_id"] == 7
        assert fields["start_lat"] == 0.0
        assert fields["time_to_pickup_seconds"] == 0
        assert fields["tariff"] == "economy"

    def test_duration_extends_end_time(self):
        fields = normalize_manual_trip(
            {"price": 500, "distance_km": 8, "duration_seconds": 900},
            now=NOW,
            default_district_id=1,
        )
        assert fields["duration_seconds"] == 900
        assert (fields["end_time"] - fields["start_time"]).total_seconds() == 900

    def test_duration_recovered_from_timestamps(self):
        start = datetime(2026, 7, 27, 10, 0, tzinfo=timezone.utc)
        end = datetime(2026, 7, 27, 10, 20, tzinfo=timezone.utc)
        fields = normalize_manual_trip(
            {"price": 500, "distance_km": 8, "start_time": start, "end_time": end},
            now=NOW,
            default_district_id=1,
        )
        assert fields["duration_seconds"] == 1200

    def test_explicit_districts_kept(self):
        fields = normalize_manual_trip(
            {"price": 300, "distance_km": 5, "start_district_id": 3, "end_district_id": 9},
            now=NOW,
            default_district_id=1,
        )
        assert fields["start_district_id"] == 3
        assert fields["end_district_id"] == 9

    def test_zero_price_rejected(self):
        with pytest.raises(ValueError):
            normalize_manual_trip({"price": 0, "distance_km": 5}, now=NOW, default_district_id=1)

    def test_negative_distance_rejected(self):
        with pytest.raises(ValueError):
            normalize_manual_trip({"price": 100, "distance_km": -1}, now=NOW, default_district_id=1)


class TestValidators:
    def test_valid_trip_amount_ok(self):
        validate_trip_amount(100.0, 0.0)  # 0 km is allowed (short waiting trip)

    def test_expense_amount_must_be_positive(self):
        validate_expense_amount(300.0)
        for bad in (0, -50, None):
            with pytest.raises(ValueError):
                validate_expense_amount(bad)


class TestDepreciationPerKm:
    def test_known_value(self):
        # 1 500 000 ₽ car, 80% lost over 400 000 km → 3.0 ₽/km.
        assert depreciation_per_km(1_500_000) == pytest.approx(3.0)

    def test_zero_or_negative_price_is_zero(self):
        assert depreciation_per_km(0) == 0.0
        assert depreciation_per_km(-100) == 0.0

    def test_scales_linearly_with_price(self):
        assert depreciation_per_km(3_000_000) == pytest.approx(2 * depreciation_per_km(1_500_000))
