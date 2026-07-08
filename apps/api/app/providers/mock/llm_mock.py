"""Deterministic templated narrative generation — explicitly a rules engine,
not real intelligence. Same context-object shape as the live OpenAI provider,
so switching later only changes which function renders text from it, not the
prompt-assembly code in app/services/.
"""
from __future__ import annotations

from typing import Any

MODEL_NAME = "mock-template-v1"


class MockLLMProvider:
    def analyze_trip(self, context: dict[str, Any]) -> dict[str, Any]:
        trip = context["trip"]
        rolling = context.get("rolling_averages", {})
        pattern_insights = context.get("pattern_insights", [])
        best_nearby = context.get("best_nearby_district")

        sentences: list[str] = []
        missed_earnings = None

        avg_wait = rolling.get("avg_wait_time_seconds")
        if avg_wait and trip["wait_time_seconds"] > avg_wait * 1.5:
            sentences.append(
                f"Вы ждали заказ {trip['wait_time_seconds'] // 60} мин — дольше обычных "
                f"{int(avg_wait // 60)} мин в районе «{trip['start_district_name']}»."
            )
        elif avg_wait:
            sentences.append(
                f"Время ожидания заказа ({trip['wait_time_seconds'] // 60} мин) было в норме для этого района."
            )

        price_per_km = trip["price"] / max(trip["distance_km"], 0.1)
        avg_price_per_km = rolling.get("avg_price_per_km")
        if avg_price_per_km:
            if price_per_km < avg_price_per_km * 0.85:
                sentences.append(
                    f"Чек за км ({price_per_km:.0f} ₽) ниже вашего среднего ({avg_price_per_km:.0f} ₽)."
                )
            elif price_per_km > avg_price_per_km * 1.15:
                sentences.append(f"Хороший чек за км: {price_per_km:.0f} ₽, выше вашего среднего.")

        if best_nearby and best_nearby["district_name"] != trip["start_district_name"]:
            sentences.append(
                f"В это время в районе «{best_nearby['district_name']}» спрос был выше "
                f"(средний чек ≈{best_nearby['expected_avg_check']:.0f} ₽)."
            )
            missed_earnings = round(
                max(0.0, best_nearby["expected_avg_check"] - trip["price"]), 2
            )

        for insight in pattern_insights[:1]:
            sentences.append(insight["pattern_text"])

        if not sentences:
            sentences.append("Поездка прошла в рамках обычных показателей — заметных отклонений нет.")

        suggested_action = None
        if best_nearby and missed_earnings and missed_earnings > 0:
            suggested_action = f"В следующий раз в это время попробуйте район «{best_nearby['district_name']}»."

        return {
            "summary_text": " ".join(sentences),
            "estimated_missed_earnings": missed_earnings,
            "suggested_action": suggested_action,
            "model_used": MODEL_NAME,
        }

    def chat(self, message: str, context: dict[str, Any]) -> str:
        text = message.lower()
        recommendation = context.get("latest_recommendation")
        today = context.get("today_finance", {})
        rolling = context.get("rolling_averages", {})

        # Order matters: check the more specific intents first. A generic
        # "где"/"where" substring check would otherwise also match "где я
        # теряю деньги?" ("where am I losing money?") and answer the wrong
        # question — caught by actually exercising the chat endpoint, not by
        # reasoning about the keyword lists in isolation.
        if any(kw in text for kw in ["теря", "losing", "потер"]):
            worst = context.get("worst_district_note")
            return worst or "Судя по вашим поездкам, явных потерь не видно — показатели ровные."

        if ("почему" in text or "why" in text) and ("доход" in text or "income" in text or "меньше" in text):
            gross = today.get("gross_income")
            avg_gross = rolling.get("avg_daily_gross_income")
            if gross is not None and avg_gross:
                diff_pct = (gross - avg_gross) / avg_gross * 100
                direction = "ниже" if diff_pct < 0 else "выше"
                return (
                    f"Сегодняшний доход {gross:.0f} ₽ {direction} среднего ({avg_gross:.0f} ₽) на "
                    f"{abs(diff_pct):.0f}%. " + (context.get("worst_district_note") or "")
                )
            return "Пока недостаточно истории, чтобы сравнить сегодняшний доход со средним."

        if any(kw in text for kw in ["заработ", "earn"]):
            if recommendation:
                return (
                    f"Чтобы заработать больше, попробуйте переместиться в «{recommendation['recommended_district_name']}» "
                    f"в ближайшие {recommendation['horizon_minutes']} мин — там ожидается более высокий спрос."
                )
            return "Продолжайте работать в часы пик (утро и вечер) — это обычно даёт наибольший доход."

        if any(kw in text for kw in ["где", "куда", "where"]):
            if recommendation:
                return (
                    f"Сейчас лучше всего работать в районе «{recommendation['recommended_district_name']}» — "
                    f"вероятность высокого спроса {recommendation['probability'] * 100:.0f}%, "
                    f"средний чек ≈{recommendation['expected_avg_check']:.0f} ₽ "
                    f"(горизонт {recommendation['horizon_minutes']} мин)."
                )
            return "Пока недостаточно данных для рекомендации — начните смену, и я подскажу лучший район."

        return (
            "Я — ваш AI-ассистент по доходу. Спросите, где сейчас лучше работать, "
            "стоит ли ехать в аэропорт, или почему доход отличается от обычного."
        )
