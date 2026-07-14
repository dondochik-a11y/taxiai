"""Trust filtering and aggregation of radar kef readings — the pure half of
the radar surge source (app/services/surge_service.py). DB-free by design."""
from decimal import Decimal

from app.services.surge_service import aggregate_kef, radar_reading_value


class TestRadarReadingValue:
    def test_range_returns_midpoint(self):
        assert radar_reading_value(1.2, 1.8) == 1.5

    def test_single_value_read(self):
        # kef_service.ingest sets kef_max = kef_min when the bubble shows one number
        assert radar_reading_value(1.4, 1.4) == 1.4

    def test_inverted_range_is_swapped(self):
        assert radar_reading_value(1.8, 1.2) == 1.5

    def test_ocr_misread_rejected(self):
        # "18" read instead of "1.8" — passes the ingest schema, not this filter
        assert radar_reading_value(1.2, 18.0) is None

    def test_nonpositive_min_rejected(self):
        assert radar_reading_value(0.0, 1.5) is None

    def test_clamped_to_one(self):
        assert radar_reading_value(0.5, 0.9) == 1.0

    def test_accepts_decimal_from_numeric_columns(self):
        assert radar_reading_value(Decimal("1.20"), Decimal("1.80")) == 1.5


class TestAggregateKef:
    def test_single_value(self):
        assert aggregate_kef([1.5]) == 1.5

    def test_median_kills_outlier(self):
        assert aggregate_kef([1.4, 1.5, 5.9]) == 1.5

    def test_even_count_averages_middle_pair(self):
        assert aggregate_kef([1.0, 1.2, 1.4, 1.6]) == 1.3

    def test_rounded_to_two_decimals(self):
        assert aggregate_kef([1.333333]) == 1.33

    def test_empty_returns_none(self):
        assert aggregate_kef([]) is None
