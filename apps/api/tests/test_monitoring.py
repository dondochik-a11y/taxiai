"""Pure observability decisions — the threshold/throttle logic behind the model
staleness watchdog, the kef coverage-gap watchdog and the persisted metrics row
shape. DB-free and clock-injected, mirroring test_radar_surge.py."""
from datetime import datetime, timedelta, timezone

from app.services import monitoring

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


class TestIsModelStale:
    def test_fresh_model_not_stale(self):
        assert monitoring.is_model_stale(NOW - timedelta(days=3), NOW) is False

    def test_old_model_is_stale(self):
        assert monitoring.is_model_stale(NOW - timedelta(days=9), NOW) is True

    def test_exactly_at_threshold_is_stale(self):
        assert monitoring.is_model_stale(NOW - monitoring.MODEL_STALE_AFTER, NOW) is True

    def test_missing_trained_at_is_stale(self):
        # "retrain never ran / no artifact" is itself the alert-worthy signal.
        assert monitoring.is_model_stale(None, NOW) is True

    def test_weekly_cadence_stays_fresh(self):
        # A healthy weekly retrain (7 days) must never false-alarm before day 8.
        assert monitoring.is_model_stale(NOW - timedelta(days=7, hours=12), NOW) is False


class TestShouldAlertStaleness:
    def test_fresh_to_stale_edge_alerts(self):
        assert monitoring.should_alert_staleness(True, False, NOW, None) is True

    def test_recovery_alerts(self):
        assert monitoring.should_alert_staleness(False, True, NOW, NOW - timedelta(days=1)) is True

    def test_healthy_stays_silent(self):
        assert monitoring.should_alert_staleness(False, False, NOW, None) is False

    def test_still_stale_within_throttle_silent(self):
        last = NOW - timedelta(hours=6)
        assert monitoring.should_alert_staleness(True, True, NOW, last) is False

    def test_still_stale_past_throttle_realerts(self):
        last = NOW - timedelta(days=3)
        assert monitoring.should_alert_staleness(True, True, NOW, last) is True


class TestClassifyRadarCoverage:
    def test_healthy_full_coverage_ok(self):
        assert monitoring.classify_radar_coverage(120, 200) == "ok"

    def test_at_floor_is_ok(self):
        assert monitoring.classify_radar_coverage(monitoring.RADAR_COVERAGE_FLOOR, 50) == "ok"

    def test_partial_coverage_degraded(self):
        # The multi-hour-gap case the old total-blackout check missed.
        assert monitoring.classify_radar_coverage(40, 30) == "degraded"

    def test_below_min_is_down(self):
        assert monitoring.classify_radar_coverage(5, 10) == "down"

    def test_no_recent_rows_is_down_even_if_hour_looks_ok(self):
        # Stale-but-present hourly coverage while the pipeline has actually gone
        # silent in the last window still counts as down.
        assert monitoring.classify_radar_coverage(90, 0) == "down"


class TestShouldAlertRadar:
    def test_ok_stays_silent(self):
        assert monitoring.should_alert_radar("ok", "ok", NOW, None) is False

    def test_newly_degraded_alerts(self):
        assert monitoring.should_alert_radar("degraded", "ok", NOW, None) is True

    def test_recovery_alerts(self):
        assert monitoring.should_alert_radar("ok", "down", NOW, NOW - timedelta(hours=1)) is True

    def test_worsening_alerts_immediately(self):
        # degraded -> down must not wait out the throttle.
        last = NOW - timedelta(minutes=5)
        assert monitoring.should_alert_radar("down", "degraded", NOW, last) is True

    def test_ongoing_bad_within_throttle_silent(self):
        last = NOW - timedelta(minutes=30)
        assert monitoring.should_alert_radar("down", "down", NOW, last) is False

    def test_ongoing_bad_past_throttle_realerts(self):
        last = NOW - timedelta(hours=4)
        assert monitoring.should_alert_radar("down", "down", NOW, last) is True

    def test_improving_but_still_bad_is_throttled(self):
        # down -> degraded within the throttle window stays quiet (not silent
        # forever: it re-alerts once the window elapses).
        last = NOW - timedelta(minutes=10)
        assert monitoring.should_alert_radar("degraded", "down", NOW, last) is False


class TestBuildMaeByHorizon:
    def test_stringifies_keys_and_rounds(self):
        out = monitoring.build_mae_by_horizon({15: 0.123456, 30: 0.2})
        assert out == {"15": 0.1235, "30": 0.2}

    def test_skips_horizons_without_holdout_rows(self):
        out = monitoring.build_mae_by_horizon({15: 0.1, 30: None, 60: 0.3})
        assert out == {"15": 0.1, "60": 0.3}

    def test_empty_mapping(self):
        assert monitoring.build_mae_by_horizon({}) == {}


class TestModelMetricShape:
    """The persisted row train_demand_model writes must carry exactly the
    fields the /health surface and staleness watchdog read back."""

    def test_table_has_expected_columns(self):
        from app.models.model_metrics import ModelMetric

        cols = set(ModelMetric.__table__.columns.keys())
        assert cols == {
            "id",
            "trained_at",
            "model_version",
            "holdout_mae",
            "mae_by_horizon",
            "train_rows",
            "holdout_rows",
        }

    def test_row_constructs_with_metrics_payload(self):
        from app.models.model_metrics import ModelMetric

        row = ModelMetric(
            model_version="hgbr-v2",
            holdout_mae=0.1234,
            mae_by_horizon=monitoring.build_mae_by_horizon({15: 0.1, 30: 0.15}),
            train_rows=900_000,
            holdout_rows=250_000,
        )
        assert row.mae_by_horizon == {"15": 0.1, "30": 0.15}
        assert row.model_version == "hgbr-v2"
