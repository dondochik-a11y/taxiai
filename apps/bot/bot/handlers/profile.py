"""/profile — lets a bot-first user (created with bare defaults by /start)
fill in everything the web onboarding form asks for, directly in Telegram:
car, tariff, fuel, rental cost, home district, work schedule. Step-by-step
FSM wizard; every step can be skipped, and only fields actually answered are
sent to the backend's PATCH /v1/users/{id} (partial update — untouched
fields keep whatever they were).
"""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import api_client

router = Router(name="profile")

SKIP_TEXT = "Пропустить"
SKIP_DATA = "skip"

# Which work_schedule keys (mon..sun) each schedule-days answer maps to.
SCHEDULE_DAY_SETS = {
    "пн–пт": ["mon", "tue", "wed", "thu", "fri"],
    "каждый день": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    "выходные": ["sat", "sun"],
}
DEFAULT_SCHEDULE_DAYS = "пн–пт"

TARIFFS = ["economy", "comfort", "comfort_plus", "business"]
FUEL_TYPES = ["petrol92", "petrol95", "diesel", "gas", "electric"]


class ProfileStates(StatesGroup):
    car_make = State()
    car_model = State()
    tariff = State()
    fuel_type = State()
    fuel_consumption = State()
    fuel_price = State()
    rental_cost = State()
    home_district = State()
    schedule_days = State()
    schedule_start = State()
    schedule_end = State()


STEPS = [
    {"state": ProfileStates.car_make, "field": "car_make", "kind": "text", "prompt": "Марка машины? (например, Hyundai)"},
    {"state": ProfileStates.car_model, "field": "car_model", "kind": "text", "prompt": "Модель машины?"},
    {"state": ProfileStates.tariff, "field": "tariff_plan", "kind": "choice", "options": TARIFFS, "prompt": "Тариф?"},
    {"state": ProfileStates.fuel_type, "field": "fuel_type", "kind": "choice", "options": FUEL_TYPES, "prompt": "Тип топлива?"},
    {"state": ProfileStates.fuel_consumption, "field": "fuel_consumption_l_per_100km", "kind": "float", "prompt": "Расход топлива, л/100км? (например, 7.5)"},
    {"state": ProfileStates.fuel_price, "field": "fuel_price_per_liter", "kind": "float", "prompt": "Цена топлива, ₽/л?"},
    {"state": ProfileStates.rental_cost, "field": "rental_cost_per_day", "kind": "float", "prompt": "Аренда, ₽/день?"},
    {"state": ProfileStates.home_district, "field": "home_district_id", "kind": "district", "prompt": "Домашний район?"},
    {"state": ProfileStates.schedule_days, "field": "_schedule_days", "kind": "choice", "options": list(SCHEDULE_DAY_SETS), "prompt": "В какие дни обычно работаете?"},
    {"state": ProfileStates.schedule_start, "field": "_schedule_start", "kind": "text", "prompt": "Во сколько обычно начинаете смену? (например, 08:00)"},
    {"state": ProfileStates.schedule_end, "field": "_schedule_end", "kind": "text", "prompt": "Во сколько обычно заканчиваете смену? (например, 20:00)"},
]
_TEXT_STATES = [s["state"] for s in STEPS if s["kind"] in ("text", "float")]
_CHOICE_STATES = [s["state"] for s in STEPS if s["kind"] in ("choice", "district")]


def _parse_float(text: str) -> float | None:
    try:
        return float(text.replace(",", "."))
    except (TypeError, ValueError):
        return None


def _skip_row() -> list[InlineKeyboardButton]:
    return [InlineKeyboardButton(text=SKIP_TEXT, callback_data=SKIP_DATA)]


def _choice_keyboard(options: list[str]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=o, callback_data=f"choice:{o}")] for o in options]
    rows.append(_skip_row())
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("profile"))
async def start_profile(message: Message, state: FSMContext) -> None:
    await state.clear()
    user = await api_client.link_telegram_user(message.from_user.id)
    profile = user.get("driver_profile") or {}
    summary = (
        f"Текущий профиль:\n"
        f"Машина: {profile.get('car_make') or '—'} {profile.get('car_model') or ''}\n"
        f"Тариф: {profile.get('tariff_plan')}, топливо: {profile.get('fuel_type')}\n"
        f"Аренда: {profile.get('rental_cost_per_day') or '—'} ₽/день\n\n"
        f"Заполним по шагам — «{SKIP_TEXT}» пропускает шаг, /cancel выходит из заполнения."
    )
    await message.answer(summary)
    await _advance(message, message.from_user.id, state, 0)


@router.message(Command("cancel"), StateFilter("*"))
async def cancel_profile(message: Message, state: FSMContext) -> None:
    """Escape hatch from the step-by-step wizard — works in any step. Without
    it, a user who abandoned /profile stays 'inside' the wizard and every
    later message (including questions meant for the AI chat) gets captured as
    a profile answer."""
    if await state.get_state() is None:
        await message.answer("Сейчас нечего отменять. Просто напишите вопрос — отвечу.")
        return
    await state.clear()
    await message.answer("Вышли из заполнения профиля. Теперь можно задавать вопросы — например, «где сейчас лучше работать?».")


async def _advance(reply_target: Message, telegram_id: int, state: FSMContext, step_index: int) -> None:
    if step_index >= len(STEPS):
        await _finish_profile(reply_target, telegram_id, state)
        return

    step = STEPS[step_index]
    await state.update_data(_step_index=step_index)
    await state.set_state(step["state"])

    if step["kind"] == "choice":
        await reply_target.answer(step["prompt"], reply_markup=_choice_keyboard(step["options"]))
    elif step["kind"] == "district":
        districts = await api_client.get_districts()
        await state.update_data(_districts={d["name"]: d["id"] for d in districts})
        await reply_target.answer(step["prompt"], reply_markup=_choice_keyboard([d["name"] for d in districts]))
    else:
        await reply_target.answer(f"{step['prompt']}\n(«-» — пропустить · /cancel — выйти)")


@router.message(StateFilter(*_TEXT_STATES))
async def handle_text_step(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    # Don't swallow an unknown command as a profile answer — commands the bot
    # knows (/profile, /link, /cancel) are handled by earlier routers/handlers
    # and never reach here; anything else starting with "/" is a mistake.
    if text.startswith("/"):
        await message.answer("Идёт пошаговое заполнение профиля. /cancel — выйти.")
        return

    data = await state.get_data()
    step_index = data["_step_index"]
    step = STEPS[step_index]

    if text not in ("-", "—", ""):
        if step["kind"] == "float":
            value = _parse_float(text)
            if value is not None:
                await state.update_data(**{step["field"]: value})
        else:
            await state.update_data(**{step["field"]: text})

    await _advance(message, message.from_user.id, state, step_index + 1)


@router.callback_query(StateFilter(*_CHOICE_STATES))
async def handle_choice_step(callback: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    step_index = data["_step_index"]
    step = STEPS[step_index]

    if callback.data != SKIP_DATA:
        _, value = callback.data.split(":", 1)
        if step["kind"] == "district":
            district_id = data.get("_districts", {}).get(value)
            if district_id is not None:
                await state.update_data(**{step["field"]: district_id})
        else:
            await state.update_data(**{step["field"]: value})

    await callback.answer()
    await _advance(callback.message, callback.from_user.id, state, step_index + 1)


async def _finish_profile(reply_target: Message, telegram_id: int, state: FSMContext) -> None:
    data = await state.get_data()

    profile_update: dict = {}
    for key in (
        "car_make",
        "car_model",
        "tariff_plan",
        "fuel_type",
        "fuel_consumption_l_per_100km",
        "fuel_price_per_liter",
        "rental_cost_per_day",
        "home_district_id",
    ):
        if key in data:
            profile_update[key] = data[key]

    start, end = data.get("_schedule_start"), data.get("_schedule_end")
    if start and end and start not in ("-", "—") and end not in ("-", "—"):
        days = SCHEDULE_DAY_SETS.get(data.get("_schedule_days"), SCHEDULE_DAY_SETS[DEFAULT_SCHEDULE_DAYS])
        profile_update["work_schedule"] = {day: [f"{start}-{end}"] for day in days}

    await state.clear()

    if not profile_update:
        await reply_target.answer("Ничего не изменилось — все шаги были пропущены.")
        return

    user = await api_client.link_telegram_user(telegram_id)
    await api_client.update_profile(user["id"], profile_update)
    await reply_target.answer("Готово, профиль обновлён! Можно посмотреть рекомендации и финансы в веб-приложении.")
