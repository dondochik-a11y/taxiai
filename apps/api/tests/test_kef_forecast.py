"""Real-data grounding of forecasts and the radar spatial fill — the pure
halves of app/ml/inference.py and app/services/{kef_profile,surge}_service.
DB-free by design, like test_radar_surge.py."""
from datetime import datetime, timezone

from app.ml.inference import blend_surge
from app.services.kef_profile_service import MIN_CELL_SAMPLES, profile_kef
from app.services.surge_service import nearest_surge_median


class TestBlendSurge:
    def test_no_real_data_passes_model_value_through(self):
        assert blend_surge(1.9, None, None, 30) == (1.9, False)

    def test_anchor_only_holds_current_kef(self):
        assert blend_surge(1.9, 1.4, None, 30) == (1.4, True)

    def test_profile_only_uses_profile(self):
        assert blend_surge(1.9, None, 1.6, 30) == (1.6, True)

    def test_short_horizon_leans_on_anchor(self):
        # 15 min: 0.85 * 2.0 + 0.15 * 1.0
        assert blend_surge(1.9, 2.0, 1.0, 15) == (1.85, True)

    def test_long_horizon_leans_on_profile(self):
        # 120 min: 0.3 * 2.0 + 0.7 * 1.0
        assert blend_surge(1.9, 2.0, 1.0, 120) == (1.3, True)


class TestProfileKef:
    # Friday 2026-07-17 18:30 Moscow == 15:30 UTC; weekday 4, hour 18 local.
    TARGET = datetime(2026, 7, 17, 15, 30, tzinfo=timezone.utc)

    def test_exact_cell_wins(self):
        profiles = {
            "exact": {(7, 4, 18): (1.8, MIN_CELL_SAMPLES)},
            "district_hour": {(7, 18): 1.4},
            "city_hour": {(4, 18): 1.2},
        }
        assert profile_kef(profiles, 7, self.TARGET) == 1.8

    def test_thin_cell_falls_back_to_district_hour(self):
        profiles = {
            "exact": {(7, 4, 18): (1.8, MIN_CELL_SAMPLES - 1)},
            "district_hour": {(7, 18): 1.4},
            "city_hour": {(4, 18): 1.2},
        }
        assert profile_kef(profiles, 7, self.TARGET) == 1.4

    def test_unknown_district_falls_back_to_city_hour(self):
        profiles = {"exact": {}, "district_hour": {}, "city_hour": {(4, 18): 1.2}}
        assert profile_kef(profiles, 7, self.TARGET) == 1.2

    def test_empty_history_returns_none(self):
        profiles = {"exact": {}, "district_hour": {}, "city_hour": {}}
        assert profile_kef(profiles, 7, self.TARGET) is None

    def test_moscow_local_hour_used(self):
        # 22:30 UTC is 01:30 MSK *next day* (Saturday, weekday 5, hour 1)
        profiles = {"exact": {}, "district_hour": {}, "city_hour": {(5, 1): 1.1}}
        target = datetime(2026, 7, 17, 22, 30, tzinfo=timezone.utc)
        assert profile_kef(profiles, 7, target) == 1.1


class TestNearestSurgeMedian:
    def test_takes_nearest_k(self):
        covered = [
            (55.70, 37.60, 1.0),
            (55.71, 37.61, 2.0),
            (55.72, 37.62, 3.0),
            (55.90, 37.90, 9.0),  # far outlier never reaches the k=3 window
        ]
        assert nearest_surge_median(55.71, 37.61, covered, k=3) == 2.0

    def test_empty_covered_returns_none(self):
        assert nearest_surge_median(55.7, 37.6, [], k=5) is None
