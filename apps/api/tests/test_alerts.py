"""Pure decision logic behind the proactive «рядом скачок спроса» push — the
nearby-set selection, the real-source-only + threshold gate, the per-district
cooldown throttle and the shift-window gate. DB-free and clock-injected,
mirroring test_monitoring.py / test_radar_surge.py."""
from datetime import datetime, timedelta, timezone

from app.services import alerts

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)  # a Monday

# A tiny synthetic Moscow-ish layout. Home (1) sits at the centre; 2/3 are
# close, 4 is a bit further, 5 is far out. Distances are equirectangular.
CENTROIDS = {
    1: (55.75, 37.60),  # home
    2: (55.76, 37.61),  # ~NE, near
    3: (55.74, 37.59),  # ~SW, near
    4: (55.78, 37.60),  # ~N, medium
    5: (55.90, 37.90),  # far
}


class TestNearbyDistrictIds:
    def test_includes_home_and_k_nearest(self):
        nearby = alerts.nearby_district_ids(1, CENTROIDS, k=2)
        assert 1 in nearby
        assert nearby == {1, 2, 3}  # the two closest neighbours, not 4/5

    def test_far_district_excluded(self):
        assert 5 not in alerts.nearby_district_ids(1, CENTROIDS, k=2)

    def test_larger_k_pulls_in_more(self):
        assert alerts.nearby_district_ids(1, CENTROIDS, k=3) == {1, 2, 3, 4}

    def test_unknown_home_yields_empty(self):
        assert alerts.nearby_district_ids(999, CENTROIDS) == set()

    def test_k_capped_by_available(self):
        # k larger than the neighbour count just returns everyone once.
        assert alerts.nearby_district_ids(1, CENTROIDS, k=99) == {1, 2, 3, 4, 5}


class TestSurgeAlertDue:
    def test_real_source_above_threshold_fires(self):
        assert alerts.surge_alert_due(1.8, "radar", 1.5) is True

    def test_real_source_at_threshold_fires(self):
        assert alerts.surge_alert_due(1.5, "radar_stale", 1.5) is True

    def test_below_threshold_silent(self):
        assert alerts.surge_alert_due(1.4, "radar", 1.5) is False

    def test_synthetic_never_fires_even_when_high(self):
        # The whole point is real data — a synthetic 3.0 must stay silent.
        assert alerts.surge_alert_due(3.0, "synthetic", 1.5) is False

    def test_live_source_never_fires(self):
        assert alerts.surge_alert_due(3.0, "live", 1.5) is False

    def test_radar_near_counts_as_real(self):
        assert alerts.surge_alert_due(2.0, "radar_near", 1.5) is True


class TestInCooldown:
    def test_never_sent_not_in_cooldown(self):
        assert alerts.in_cooldown(None, NOW) is False

    def test_recent_send_is_in_cooldown(self):
        assert alerts.in_cooldown(NOW - timedelta(minutes=20), NOW) is True

    def test_past_cooldown_clears(self):
        assert alerts.in_cooldown(NOW - timedelta(minutes=46), NOW) is False

    def test_exactly_at_cooldown_clears(self):
        assert alerts.in_cooldown(NOW - alerts.PROXIMITY_COOLDOWN, NOW) is False


class TestIsWithinShift:
    SCHEDULE = {"mon": ["08:00-20:00"]}

    def test_inside_window(self):
        assert alerts.is_within_shift(self.SCHEDULE, 0, 12) is True

    def test_at_start_hour(self):
        assert alerts.is_within_shift(self.SCHEDULE, 0, 8) is True

    def test_before_start(self):
        assert alerts.is_within_shift(self.SCHEDULE, 0, 7) is False

    def test_at_end_hour_excluded(self):
        assert alerts.is_within_shift(self.SCHEDULE, 0, 20) is False

    def test_day_off_when_weekday_empty(self):
        # A schedule exists but Tuesday is empty → explicit day off.
        assert alerts.is_within_shift(self.SCHEDULE, 1, 12) is False

    def test_no_schedule_is_always_on(self):
        assert alerts.is_within_shift({}, 0, 3) is True


class TestSelectSurgeAlerts:
    NEARBY = {1, 2, 3}

    def _surge(self, overrides):
        base = {
            1: {"surge": 1.2, "source": "radar"},
            2: {"surge": 1.9, "source": "radar"},
            3: {"surge": 2.5, "source": "synthetic"},
        }
        base.update(overrides)
        return base

    def test_only_real_over_threshold_selected(self):
        # 1 too low, 2 qualifies, 3 is synthetic (never), 4 not nearby.
        surge = self._surge({4: {"surge": 3.0, "source": "radar"}})
        due = alerts.select_surge_alerts(self.NEARBY, surge, 1.5, {}, NOW)
        assert due == [2]

    def test_cooldown_suppresses_recent_district(self):
        surge = self._surge({1: {"surge": 2.0, "source": "radar"}})
        last_sent = {2: NOW - timedelta(minutes=10)}  # 2 still cooling down
        due = alerts.select_surge_alerts(self.NEARBY, surge, 1.5, last_sent, NOW)
        assert due == [1]  # 1 now qualifies and was never sent; 2 throttled

    def test_expired_cooldown_lets_it_through_again(self):
        surge = self._surge({})
        last_sent = {2: NOW - timedelta(minutes=50)}  # past the 45-min window
        due = alerts.select_surge_alerts(self.NEARBY, surge, 1.5, last_sent, NOW)
        assert due == [2]

    def test_threshold_is_per_driver(self):
        surge = self._surge({})  # district 2 at 1.9
        assert alerts.select_surge_alerts(self.NEARBY, surge, 2.0, {}, NOW) == []
        assert alerts.select_surge_alerts(self.NEARBY, surge, 1.9, {}, NOW) == [2]

    def test_missing_surge_row_skipped(self):
        due = alerts.select_surge_alerts({1, 2, 3, 99}, self._surge({}), 1.5, {}, NOW)
        assert 99 not in due


class TestDirectionAndDistance:
    def test_distance_is_positive_km(self):
        d = alerts.distance_km(55.75, 37.60, 55.78, 37.60)
        assert 3.0 < d < 3.5  # ~0.03° lat ≈ 3.3 km

    def test_direction_north(self):
        assert alerts.direction_hint(55.75, 37.60, 55.80, 37.60) == "С"

    def test_direction_east(self):
        assert alerts.direction_hint(55.75, 37.60, 55.75, 37.70) == "В"

    def test_direction_none_for_same_point(self):
        assert alerts.direction_hint(55.75, 37.60, 55.75, 37.60) is None
