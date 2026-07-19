"""Tests for the pure rendering helpers (bot/render.py) — no network, no
aiogram, no Telegram token needed."""
from __future__ import annotations

from bot.render import (
    map_url,
    render_daily_plan,
    render_finance_summary,
    render_kef_table,
    render_ocr_result,
    render_recommendation,
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
            "rationale_text": "Через 30 мин в районе «Арбат» ожидается повышенный спрос.",
        },
        DISTRICTS,
    )
    assert "Стоит ехать в «Арбат»" in text
    assert "72%" in text
    assert "640 ₽" in text
    assert "повышенный спрос" in text


def test_recommendation_stay_and_unknown_district() -> None:
    text = render_recommendation(
        {
            "action": "stay",
            "recommended_district_id": 99,
            "recommended_horizon_minutes": 30,
            "probability": 0.4,
            "expected_avg_check": 500.0,
            "rationale_text": None,
        },
        DISTRICTS,
    )
    assert "Оставайтесь" in text
    assert "район #99" in text


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
