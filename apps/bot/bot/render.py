"""Pure text-rendering helpers: backend JSON in, Russian strings out.
No aiogram, no HTTP — keeps handlers thin and lets the formatting be
unit-tested without a network or a Telegram token.
"""
from __future__ import annotations

import html
from datetime import date

# Honest labels for the surge source cascade (see
# apps/api/app/services/surge_service.py) — synthetic must never be
# presented as a real reading.
KEF_SOURCE_LABELS = {
    "radar": "реальный",
    "radar_stale": "реальный >45мин",
    "radar_near": "по соседям",
    "live": "по ценам",
    "synthetic": "синтетика",
}


def map_url(base: str, district_id: int | None = None) -> str:
    """Deep link into the PWA map (see the Phase 3 deep-link contract):
    district-focused when an id is given, plain map otherwise. `base` is the
    bot's web_base_url; a trailing slash is normalised away."""
    base = base.rstrip("/")
    if district_id is None:
        return f"{base}/"
    return f"{base}/?district={district_id}"


def render_recommendation(rec: dict, district_names: dict[int, str]) -> str:
    target_id = rec["recommended_district_id"]
    target = district_names.get(target_id, f"район #{target_id}")
    if rec.get("action") == "move":
        head = f"🧭 Стоит ехать в «{target}»."
    else:
        head = f"🧭 Оставайтесь в «{target}» — переезд сейчас не окупится."
    lines = [
        head,
        f"Вероятность заказа: {float(rec.get('probability', 0)) * 100:.0f}% · "
        f"ожидаемый чек ≈{float(rec.get('expected_avg_check', 0)):.0f} ₽ · "
        f"горизонт {rec.get('recommended_horizon_minutes', 30)} мин",
    ]
    if rec.get("rationale_text"):
        lines.append(rec["rationale_text"])
    return "\n".join(lines)


def render_kef_table(surge_rows: list[dict], district_names: dict[int, str], top_n: int = 10) -> str:
    """One compact HTML message: top districts by current kef, each row
    marked with how real its number is."""
    rows = sorted(surge_rows, key=lambda r: r["surge"], reverse=True)[:top_n]
    if not rows:
        return "Пока нет данных по кэфу — попробуйте чуть позже."

    names = [district_names.get(r["district_id"], f"#{r['district_id']}") for r in rows]
    width = max(len(n) for n in names)
    lines = [
        f"{r['surge']:>4.1f}  {html.escape(name.ljust(width))}  {KEF_SOURCE_LABELS.get(r['source'], r['source'])}"
        for r, name in zip(rows, names)
    ]
    return (
        f"Кэф по районам сейчас — топ-{len(rows)}:\n"
        "<pre>" + "\n".join(lines) + "</pre>"
    )


def render_ocr_result(result: dict, district_names: dict[int, str]) -> str:
    """Echo what the vision OCR read off a driver's surge screenshot, so the
    driver sees their contribution landed (and can spot a misread)."""
    readings = result.get("readings") or []
    if not readings:
        return (
            "Не нашёл на скрине значений кэфа. Нужен скрин карты повышенного "
            "спроса (Яндекс Про или радар) с цифрами на районах."
        )
    lines = []
    for r in readings[:10]:
        if r.get("district_id") is not None:
            place = district_names.get(r["district_id"], f"район #{r['district_id']}")
        else:
            place = r.get("area_hint") or "без привязки к району"
        kef = f"{r['kef_min']:.1f}"
        if r.get("kef_max") is not None and r["kef_max"] != r["kef_min"]:
            kef += f"–{r['kef_max']:.1f}"
        lines.append(f"• {html.escape(place)}: {kef}")
    extra = f"\n…и ещё {len(readings) - 10}." if len(readings) > 10 else ""
    return (
        f"📷 Прочитал кэф со скрина — записал {result.get('stored', len(readings))} "
        f"значений, привязал к районам: {result.get('resolved_districts', 0)}.\n"
        + "\n".join(lines)
        + extra
        + "\n\nСпасибо! Эти данные улучшают карту для всех."
    )


def render_finance_summary(summary: dict) -> str:
    if not summary or not summary.get("trips_count"):
        return "Пока нет поездок за сегодня — итоги появятся после первой записанной поездки."

    day = date.fromisoformat(str(summary["summary_date"])).strftime("%d.%m")
    return (
        f"💰 Итоги за {day}:\n"
        f"Поездок: {summary['trips_count']} · онлайн {summary['online_hours']:.1f} ч\n"
        f"Доход: {summary['gross_income']:.0f} ₽ · чистыми: {summary['net_income']:.0f} ₽\n"
        f"Расходы: топливо {summary['fuel_cost']:.0f} ₽ · аренда {summary['rental_cost']:.0f} ₽ · "
        f"мойка {summary['wash_cost']:.0f} ₽ · штрафы {summary['fines_cost']:.0f} ₽\n"
        f"Налог ≈{summary['tax_estimate']:.0f} ₽ · амортизация ≈{summary['depreciation_estimate']:.0f} ₽\n"
        f"Темп: {summary['income_per_hour']:.0f} ₽/час · {summary['income_per_km']:.0f} ₽/км"
    )


def render_daily_plan(windows: list[dict]) -> str:
    if not windows:
        return "Пока не хватает данных для плана на сегодня — загляните позже."
    lines = [f"• {w['start_hour']:02d}:00–{w['end_hour']:02d}:00" for w in windows]
    return (
        "📅 Лучшие окна для работы сегодня:\n"
        + "\n".join(lines)
        + "\n\nОценка по историческим данным для этого дня недели."
    )
