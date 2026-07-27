"""Pure decision helpers of recommendation_service — the uplift/validity math
surfaced in Phase 4. DB-free by design, like test_kef_forecast.py: the models
lean on PostGIS/PG enums, so the logic worth testing is factored out of the
DB-bound generate_recommendation() into standalone functions."""
from datetime import datetime, timezone

from app.services.recommendation_service import (
    MOVE_THRESHOLD_PCT,
    _compute_uplift_pct,
    _resolve_move,
    _valid_until,
)


class _Forecast:
    """Minimal stand-in for the Forecast ORM row — only target_time is read."""

    def __init__(self, target_time: datetime) -> None:
        self.target_time = target_time


class TestComputeUpliftPct:
    def test_ratio_over_baseline(self):
        assert _compute_uplift_pct(1000.0, 1180.0) == 18.0

    def test_zero_baseline_is_full_uplift(self):
        # Staying earns nothing → any positive best district is a 100% uplift.
        assert _compute_uplift_pct(0.0, 500.0) == 100.0


class TestResolveMove:
    def test_move_uplift_matches_computed_gain(self):
        # A different district clearing the threshold → "move" carrying the gain.
        action, uplift = _resolve_move(1000.0, 1180.0, is_different_district=True)
        assert action == "move"
        assert uplift == 18.0
        assert uplift == round(_compute_uplift_pct(1000.0, 1180.0), 1)

    def test_gain_below_threshold_stays_with_no_uplift(self):
        # 10% < 15% threshold → don't move, and advertise no uplift.
        gain = _compute_uplift_pct(1000.0, 1100.0)
        assert gain < MOVE_THRESHOLD_PCT
        action, uplift = _resolve_move(1000.0, 1100.0, is_different_district=True)
        assert action == "stay"
        assert uplift is None

    def test_same_district_is_a_stay_with_no_uplift(self):
        action, uplift = _resolve_move(1000.0, 1000.0, is_different_district=False)
        assert action == "stay"
        assert uplift is None

    def test_threshold_boundary_moves(self):
        # Exactly at the threshold counts as a move (>=).
        action, uplift = _resolve_move(1000.0, 1150.0, is_different_district=True)
        assert action == "move"
        assert uplift == MOVE_THRESHOLD_PCT


class TestValidUntil:
    def test_uses_forecast_target_time(self):
        target = datetime(2026, 7, 27, 9, 30, tzinfo=timezone.utc)
        assert _valid_until(_Forecast(target)) == target

    def test_none_forecast_yields_none(self):
        assert _valid_until(None) is None
