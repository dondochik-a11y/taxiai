"""Pure text-rendering helpers: backend JSON in, Russian strings out.
No aiogram, no HTTP — keeps handlers thin and lets the formatting be
unit-tested without a network or a Telegram token.
"""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone

# Recommendations quote their validity window in Moscow time (drivers are in
# Moscow; the backend stores UTC). MSK is a fixed UTC+3, no DST.
MSK = timezone(timedelta(hours=3))

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


def _fmt_valid_until(raw: str | None) -> str | None:
    """ISO timestamp (UTC) from the backend → 'HH:MM' in Moscow time, or None."""
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(MSK).strftime("%H:%M")


# /alert threshold bounds — a Yandex kef realistically lives in ~1.0–4.0;
# reject anything outside a generous 1.0–6.0 as a typo (mirrors the ingest
# RADAR_KEF_MAX_PLAUSIBLE on the backend).
ALERT_MIN_THRESHOLD = 1.0
ALERT_MAX_THRESHOLD = 6.0


def parse_alert_arg(arg: str | None) -> dict:
    """Parse the /alert command argument into an action for the handler.
    No I/O — the handler applies the result. Returns one of:
      {"action": "show"} — no arg, just report current state;
      {"action": "on"} / {"action": "off"} — toggle;
      {"action": "set", "threshold": float} — set threshold (and enable);
      {"action": "invalid"} — unparseable / out-of-range."""
    text = (arg or "").strip().lower()
    if text == "":
        return {"action": "show"}
    if text in ("off", "выкл", "стоп", "0"):
        return {"action": "off"}
    if text in ("on", "вкл"):
        return {"action": "on"}
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        return {"action": "invalid"}
    if not (ALERT_MIN_THRESHOLD <= value <= ALERT_MAX_THRESHOLD):
        return {"action": "invalid"}
    return {"action": "set", "threshold": round(value, 1)}


def render_alert_status(enabled: bool, threshold: float) -> str:
    state = "включены ✅" if enabled else "выключены ⛔️"
    return (
        f"🚀 Оповещения «рядом скачок спроса»: {state}.\n"
        f"Порог кэфа: {float(threshold):.1f}.\n\n"
        "Пришлю пуш, когда в вашем домашнем районе или рядом с ним кэф "
        "достигнет порога (только по реальным данным радара).\n"
        "Настройка: «/alert 1.7» — задать порог · «/alert off» — выключить."
    )


def render_recommendation(rec: dict, district_names: dict[int, str]) -> str:
    target_id = rec["recommended_district_id"]
    target = district_names.get(target_id, f"район #{target_id}")
    if rec.get("action") == "move":
        head = f"🧭 Стоит ехать в «{target}»."
        uplift = rec.get("expected_uplift_pct")
        if uplift is not None:
            head += f" +{float(uplift):.0f}% к ожидаемому доходу"
    else:
        head = f"🧭 Оставайтесь в «{target}» — переезд сейчас не окупится."
    lines = [
        head,
        # `probability` is a demand-level proxy, not a calibrated order
        # probability — label it honestly as «уровень спроса».
        f"Уровень спроса: {float(rec.get('probability', 0)) * 100:.0f}% · "
        f"ожидаемый чек ≈{float(rec.get('expected_avg_check', 0)):.0f} ₽ · "
        f"горизонт {rec.get('recommended_horizon_minutes', 30)} мин",
    ]
    valid_until = _fmt_valid_until(rec.get("valid_until"))
    if valid_until:
        lines.append(f"Актуально до {valid_until} (МСК)")
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


def render_model_health(health: dict) -> str:
    """Operator readout of demand-model freshness + forecast quality — backs the
    /health command. Input is GET /v1/health/model."""
    version = health.get("model_version") or "—"
    trained_raw = health.get("trained_at")
    if trained_raw:
        trained = _fmt_valid_until(trained_raw)
        age_days = health.get("age_days")
        age_txt = f"{age_days} дн. назад" if age_days is not None else "?"
        when = f"{trained} МСК ({age_txt})" if trained else age_txt
    else:
        when = "модель ещё не обучалась"

    flag = "⚠️ УСТАРЕЛА" if health.get("is_stale") else "✅ свежая"
    lines = [
        f"🩺 Модель спроса: {flag}",
        f"Версия: {version}",
        f"Обучена: {when}",
    ]

    holdout = health.get("holdout_mae")
    if holdout is not None:
        lines.append(f"Holdout MAE: {holdout:.4f}")
    by_h = health.get("mae_by_horizon") or {}
    if by_h:
        order = sorted(by_h.items(), key=lambda kv: int(kv[0]))
        lines.append("MAE по горизонтам: " + ", ".join(f"{h}м {float(v):.3f}" for h, v in order))
    rows = health.get("holdout_rows")
    if rows is not None:
        lines.append(f"Строк: обучение {health.get('train_rows')}, holdout {rows}")
    return "\n".join(lines)


def render_daily_plan(windows: list[dict]) -> str:
    if not windows:
        return "Пока не хватает данных для плана на сегодня — загляните позже."
    lines = [f"• {w['start_hour']:02d}:00–{w['end_hour']:02d}:00" for w in windows]
    return (
        "📅 Лучшие окна для работы сегодня:\n"
        + "\n".join(lines)
        + "\n\nОценка по историческим данным для этого дня недели."
    )
