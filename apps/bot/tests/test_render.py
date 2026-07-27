"""Tests for the pure rendering helpers (bot/render.py) — no network, no
aiogram, no Telegram token needed."""
from __future__ import annotations

from bot.render import (
    map_url,
    parse_alert_arg,
    parse_expense,
    parse_expense_amount,
    parse_goal_arg,
    parse_trip_amount,
    parse_trip_distance,
    parse_trip_quicklog,
    render_alert_status,
    render_daily_plan,
    render_expense_invalid,
    render_expense_logged,
    render_finance_summary,
    render_goal_cleared,
    render_goal_progress,
    render_goal_set,
    render_kef_table,
    render_model_health,
    render_ocr_result,
    render_recommendation,
    render_shift_started,
    render_shift_stopped,
    render_trip_invalid,
    render_trip_logged,
)

DISTRICTS = {1: "Хамовники", 2: "Арбат", 3: "Тверской"}

BASE = "https://93.189.228.203.sslip.io"


def test_map_url_with_district() -> None:
    assert map_url(BASE, 7) == "https://93.189.228.203.sslip.io/?district=7"


def test_map_url_without_district() -> None:
    assert map_url(BASE) == "https://93.189.228.203.sslip.io/"
    assert map_url(BASE, None) == "https://93.189.228.203.sslip.io/"


def test_map_url_normalises_trailing_slash() -> None:
    assert map_url(BASE + "/", 3) == "https://93.189.228.203.sslip.io/?district=3"
    assert map_url(BASE + "/") == "https://93.189.228.203.sslip.io/"


def test_recommendation_move() -> None:
    text = render_recommendation(
        {
            "action": "move",
            "recommended_district_id": 2,
            "recommended_horizon_minutes": 30,
            "probability": 0.72,
            "expected_avg_check": 640.0,
            "expected_uplift_pct": 18.0,
            "valid_until": "2026-07-27T09:30:00+00:00",  # 09:30 UTC → 12:30 MSK
            "rationale_text": "Через 30 мин в районе «Арбат» ожидается повышенный спрос.",
        },
        DISTRICTS,
    )
    assert "Стоит ехать в «Арбат»" in text
    assert "+18% к ожидаемому доходу" in text
    # `probability` is a demand-level proxy — must not be sold as order probability.
    assert "Уровень спроса" in text
    assert "72%" in text
    assert "Вероятность заказа" not in text
    assert "640 ₽" in text
    assert "Актуально до 12:30 (МСК)" in text
    assert "повышенный спрос" in text


def test_recommendation_stay_and_unknown_district() -> None:
    text = render_recommendation(
        {
            "action": "stay",
            "recommended_district_id": 99,
            "recommended_horizon_minutes": 30,
            "probability": 0.4,
            "expected_avg_check": 500.0,
            "expected_uplift_pct": None,  # staying has no uplift to advertise
            "valid_until": None,
            "rationale_text": None,
        },
        DISTRICTS,
    )
    assert "Оставайтесь" in text
    assert "район #99" in text
    # No uplift line and no validity line when the backend sends nulls.
    assert "к ожидаемому доходу" not in text
    assert "Актуально до" not in text


def test_kef_table_sorted_top_n_with_source_labels() -> None:
    rows = [
        {"district_id": 1, "surge": 1.2, "source": "radar"},
        {"district_id": 2, "surge": 2.4, "source": "synthetic"},
        {"district_id": 3, "surge": 1.7, "source": "radar_near"},
    ]
    text = render_kef_table(rows, DISTRICTS, top_n=2)
    assert "топ-2" in text
    assert "<pre>" in text and "</pre>" in text
    # Sorted desc: Арбат (2.4) first, Тверской (1.7) second, Хамовники cut off.
    assert text.index("Арбат") < text.index("Тверской")
    assert "Хамовники" not in text
    assert "синтетика" in text
    assert "по соседям" in text


def test_kef_table_all_source_labels_and_empty() -> None:
    for source, label in [
        ("radar", "реальный"),
        ("radar_stale", "реальный >45мин"),
        ("radar_near", "по соседям"),
        ("live", "по ценам"),
        ("synthetic", "синтетика"),
    ]:
        text = render_kef_table([{"district_id": 1, "surge": 1.5, "source": source}], DISTRICTS)
        assert label in text
    assert "нет данных" in render_kef_table([], DISTRICTS)


def test_finance_summary() -> None:
    text = render_finance_summary(
        {
            "summary_date": "2026-07-17",
            "gross_income": 8450.0,
            "net_income": 5210.6,
            "fuel_cost": 1200.0,
            "rental_cost": 1500.0,
            "wash_cost": 0.0,
            "fines_cost": 0.0,
            "tax_estimate": 507.0,
            "depreciation_estimate": 32.5,
            "trips_count": 21,
            "online_hours": 9.5,
            "income_per_hour": 548.7,
            "income_per_km": 38.2,
        }
    )
    assert "17.07" in text
    assert "Поездок: 21" in text
    assert "чистыми: 5211 ₽" in text  # rounded, ~5210.5
    assert "549 ₽/час" in text


def test_finance_summary_empty_day() -> None:
    text = render_finance_summary({"summary_date": "2026-07-17", "trips_count": 0})
    assert "нет поездок" in text.lower()


def test_ocr_result_mixed_readings() -> None:
    text = render_ocr_result(
        {
            "stored": 3,
            "resolved_districts": 2,
            "readings": [
                {"kef_min": 1.5, "kef_max": 2.1, "district_id": 1},
                {"kef_min": 1.8, "kef_max": None, "district_id": None, "area_hint": "Марфино"},
                {"kef_min": 2.0, "kef_max": 2.0, "district_id": 99},
            ],
        },
        DISTRICTS,
    )
    assert "записал 3" in text
    assert "Хамовники: 1.5–2.1" in text
    assert "Марфино: 1.8" in text
    assert "район #99: 2.0" in text  # unknown id → honest fallback, no range for equal min/max
    assert "2.0–2.0" not in text


def test_ocr_result_empty() -> None:
    text = render_ocr_result({"stored": 0, "resolved_districts": 0, "readings": []}, DISTRICTS)
    assert "Не нашёл" in text


def test_daily_plan() -> None:
    text = render_daily_plan([{"start_hour": 7, "end_hour": 11}, {"start_hour": 18, "end_hour": 22}])
    assert "07:00–11:00" in text
    assert "18:00–22:00" in text
    assert "не хватает данных" in render_daily_plan([])


def test_model_health_fresh() -> None:
    text = render_model_health(
        {
            "model_version": "hgbr-v2",
            "trained_at": "2026-07-26T03:30:00+00:00",
            "age_days": 1.4,
            "is_stale": False,
            "holdout_mae": 0.1234,
            "mae_by_horizon": {"15": 0.10, "60": 0.19, "120": 0.24, "30": 0.15},
            "train_rows": 900000,
            "holdout_rows": 250000,
        }
    )
    assert "свежая" in text
    assert "hgbr-v2" in text
    assert "0.1234" in text
    # horizons rendered in numeric order, not dict/string order
    assert text.index("15м") < text.index("30м") < text.index("60м") < text.index("120м")


def test_model_health_stale() -> None:
    text = render_model_health(
        {
            "model_version": "hgbr-v2",
            "trained_at": "2026-07-10T03:30:00+00:00",
            "age_days": 17.3,
            "is_stale": True,
            "holdout_mae": 0.2,
            "mae_by_horizon": {},
            "train_rows": 900000,
            "holdout_rows": 250000,
        }
    )
    assert "УСТАРЕЛА" in text
    assert "17.3 дн" in text


def test_model_health_never_trained() -> None:
    text = render_model_health(
        {
            "model_version": None,
            "trained_at": None,
            "age_days": None,
            "is_stale": True,
            "holdout_mae": None,
            "mae_by_horizon": {},
            "train_rows": None,
            "holdout_rows": None,
        }
    )
    assert "УСТАРЕЛА" in text
    assert "не обучалась" in text


def test_parse_alert_arg_empty_shows() -> None:
    assert parse_alert_arg("") == {"action": "show"}
    assert parse_alert_arg(None) == {"action": "show"}


def test_parse_alert_arg_on_off() -> None:
    assert parse_alert_arg("off")["action"] == "off"
    assert parse_alert_arg("выкл")["action"] == "off"
    assert parse_alert_arg("on")["action"] == "on"


def test_parse_alert_arg_sets_threshold() -> None:
    assert parse_alert_arg("1.7") == {"action": "set", "threshold": 1.7}
    # comma decimal + surrounding whitespace both tolerated.
    assert parse_alert_arg(" 2,0 ") == {"action": "set", "threshold": 2.0}


def test_parse_alert_arg_rejects_out_of_range_and_garbage() -> None:
    assert parse_alert_arg("0.5")["action"] == "invalid"
    assert parse_alert_arg("42")["action"] == "invalid"
    assert parse_alert_arg("быстрее")["action"] == "invalid"


def test_render_alert_status_reflects_state() -> None:
    on = render_alert_status(True, 1.7)
    assert "включены" in on and "1.7" in on
    off = render_alert_status(False, 1.5)
    assert "выключены" in off and "1.5" in off


# --- /goal ------------------------------------------------------------------

_FINANCE_BASE = {
    "summary_date": "2026-07-17",
    "gross_income": 8450.0,
    "net_income": 3000.0,
    "fuel_cost": 1200.0,
    "rental_cost": 1500.0,
    "wash_cost": 0.0,
    "fines_cost": 0.0,
    "tax_estimate": 507.0,
    "depreciation_estimate": 32.5,
    "trips_count": 21,
    "online_hours": 9.5,
    "income_per_hour": 548.7,
    "income_per_km": 38.2,
}


def test_parse_goal_arg_empty_shows() -> None:
    assert parse_goal_arg("") == {"action": "show"}
    assert parse_goal_arg(None) == {"action": "show"}


def test_parse_goal_arg_clear() -> None:
    assert parse_goal_arg("off")["action"] == "clear"
    assert parse_goal_arg("выкл")["action"] == "clear"
    assert parse_goal_arg("0")["action"] == "clear"


def test_parse_goal_arg_sets_amount() -> None:
    assert parse_goal_arg("5000") == {"action": "set", "amount": 5000}
    # tolerate rubles sign, spaces and comma decimals
    assert parse_goal_arg("5 000 ₽")["amount"] == 5000
    assert parse_goal_arg("4999,6")["amount"] == 5000  # rounds to whole ruble


def test_parse_goal_arg_rejects_out_of_range_and_garbage() -> None:
    assert parse_goal_arg("50")["action"] == "invalid"  # below GOAL_MIN
    assert parse_goal_arg("99999999")["action"] == "invalid"  # above GOAL_MAX
    assert parse_goal_arg("много")["action"] == "invalid"


def test_render_goal_set_and_cleared() -> None:
    assert "5000 ₽" in render_goal_set(5000)
    assert "сброшена" in render_goal_cleared()


def test_render_goal_progress_partial() -> None:
    summary = {**_FINANCE_BASE, "daily_goal": 5000.0, "goal_remaining": 2000.0,
               "goal_reached": False, "goal_pct": 60.0}
    text = render_goal_progress(summary)
    assert "5000 ₽" in text
    assert "осталось 2000 ₽" in text
    assert "60%" in text


def test_render_goal_progress_reached() -> None:
    summary = {**_FINANCE_BASE, "net_income": 5200.0, "daily_goal": 5000.0,
               "goal_remaining": 0.0, "goal_reached": True, "goal_pct": 100.0}
    text = render_goal_progress(summary)
    assert "достигнута" in text


def test_render_goal_progress_no_goal() -> None:
    assert "не задана" in render_goal_progress({**_FINANCE_BASE, "daily_goal": None})


def test_finance_summary_surfaces_goal_remaining() -> None:
    summary = {**_FINANCE_BASE, "daily_goal": 5000.0, "goal_remaining": 2000.0,
               "goal_reached": False}
    text = render_finance_summary(summary)
    assert "осталось 2000 ₽" in text


def test_finance_summary_goal_reached_line() -> None:
    summary = {**_FINANCE_BASE, "daily_goal": 5000.0, "goal_remaining": 0.0,
               "goal_reached": True}
    assert "достигнута" in render_finance_summary(summary)


def test_finance_summary_no_goal_no_goal_line() -> None:
    text = render_finance_summary(_FINANCE_BASE)
    assert "Цель" not in text


# --- /shift -----------------------------------------------------------------


def test_render_shift_started_shows_msk_time() -> None:
    # 09:00 UTC → 12:00 MSK
    text = render_shift_started("2026-07-27T09:00:00+00:00")
    assert "Смена начата" in text
    assert "12:00 (МСК)" in text


def test_render_shift_started_without_time() -> None:
    text = render_shift_started(None)
    assert "Смена начата" in text


def test_render_shift_stopped_shows_elapsed_and_income() -> None:
    text = render_shift_stopped(
        {
            "action": "stopped",
            "elapsed_hours": 5.5,
            "trips_count_today": 12,
            "net_income_today": 4200.0,
            "gross_income_today": 6800.0,
        }
    )
    assert "5ч 30м" in text
    assert "12 поездок" in text
    assert "чистыми 4200 ₽" in text


# --- /trip quick-log (office task #101) --------------------------------------


def test_parse_trip_quicklog_inline() -> None:
    assert parse_trip_quicklog("450 12") == {
        "action": "log",
        "amount": 450.0,
        "distance_km": 12.0,
    }


def test_parse_trip_quicklog_with_units_and_duration() -> None:
    r = parse_trip_quicklog("450₽ 12км 20мин")
    assert r["action"] == "log"
    assert r["amount"] == 450.0
    assert r["distance_km"] == 12.0
    assert r["duration_seconds"] == 20 * 60


def test_parse_trip_quicklog_comma_decimal() -> None:
    assert parse_trip_quicklog("450,5 12,3")["amount"] == 450.5


def test_parse_trip_quicklog_empty_prompts() -> None:
    assert parse_trip_quicklog("")["action"] == "prompt"
    assert parse_trip_quicklog(None)["action"] == "prompt"


def test_parse_trip_quicklog_invalid() -> None:
    assert parse_trip_quicklog("450")["action"] == "invalid"  # missing distance
    assert parse_trip_quicklog("abc def")["action"] == "invalid"
    assert parse_trip_quicklog("0 5")["action"] == "invalid"  # amount below min


def test_parse_trip_amount_and_distance() -> None:
    assert parse_trip_amount("450") == 450.0
    assert parse_trip_amount("0") is None
    assert parse_trip_distance("12,5") == 12.5
    assert parse_trip_distance("-1") is None


def test_render_trip_logged() -> None:
    text = render_trip_logged({"price": 450.0, "distance_km": 12.0})
    assert "450 ₽" in text
    assert "12.0 км" in text
    assert "/finance" in text


def test_render_trip_invalid_mentions_format() -> None:
    assert "/trip 450 12" in render_trip_invalid()


# --- /expense entry (office task #101) ---------------------------------------


def test_parse_expense_inline() -> None:
    assert parse_expense("wash 300") == {"action": "log", "category": "wash", "amount": 300.0}


def test_parse_expense_russian_synonym() -> None:
    r = parse_expense("штраф 500")
    assert r == {"action": "log", "category": "fine", "amount": 500.0}


def test_parse_expense_category_only_asks_amount() -> None:
    assert parse_expense("other") == {"action": "need_amount", "category": "other"}


def test_parse_expense_empty_prompts() -> None:
    assert parse_expense("")["action"] == "prompt"


def test_parse_expense_invalid() -> None:
    assert parse_expense("groceries 300")["action"] == "invalid"  # unknown category
    assert parse_expense("wash -5")["action"] == "invalid"  # bad amount


def test_parse_expense_amount() -> None:
    assert parse_expense_amount("300") == 300.0
    assert parse_expense_amount("0") is None


def test_render_expense_logged_uses_russian_label() -> None:
    text = render_expense_logged({"category": "wash", "amount": 300.0})
    assert "мойка" in text
    assert "300 ₽" in text


def test_render_expense_invalid_lists_categories() -> None:
    text = render_expense_invalid()
    assert "wash" in text and "fine" in text and "other" in text
