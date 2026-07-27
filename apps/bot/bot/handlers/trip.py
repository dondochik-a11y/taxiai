"""/trip — quickly log a completed trip so it flows into the real finance
summary (office task #101).

  /trip                 → step-by-step: amount, then distance
  /trip 450 12          → inline: amount ₽ + distance km
  /trip 450 12 20       → …plus duration in minutes

Parsing/formatting is pure (bot/render); this handler only does the FSM plumbing
and the POST /v1/trips call (which fills every other field server-side).
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import (
    parse_trip_amount,
    parse_trip_distance,
    parse_trip_quicklog,
    render_trip_ask_distance,
    render_trip_invalid,
    render_trip_logged,
    render_trip_prompt,
)

router = Router(name="trip")

SKIP_TOKENS = ("-", "—", "")


class TripStates(StatesGroup):
    amount = State()
    distance = State()


async def _log_trip(message: Message, telegram_id: int, payload: dict) -> None:
    user = await api_client.link_telegram_user(telegram_id)
    trip = await api_client.create_trip(user["id"], payload)
    await message.answer(render_trip_logged(trip))


@router.message(Command("trip"))
async def handle_trip(message: Message, command: CommandObject, state: FSMContext) -> None:
    parsed = parse_trip_quicklog(command.args)

    if parsed["action"] == "invalid":
        await message.answer(render_trip_invalid())
        return

    if parsed["action"] == "log":
        payload = {"price": parsed["amount"], "distance_km": parsed["distance_km"]}
        if "duration_seconds" in parsed:
            payload["duration_seconds"] = parsed["duration_seconds"]
        await _log_trip(message, message.from_user.id, payload)
        return

    # action == "prompt" → start the step-by-step flow.
    await state.clear()
    await state.set_state(TripStates.amount)
    await message.answer(render_trip_prompt())


@router.message(Command("cancel"), StateFilter(TripStates.amount, TripStates.distance))
async def cancel_trip(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменил запись поездки. /trip — начать заново.")


@router.message(StateFilter(TripStates.amount))
async def trip_amount_step(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await message.answer("Записываю поездку. Отправьте сумму в ₽ или /cancel.")
        return
    amount = parse_trip_amount(text)
    if amount is None:
        await message.answer(render_trip_invalid())
        return
    await state.update_data(amount=amount)
    await state.set_state(TripStates.distance)
    await message.answer(render_trip_ask_distance())


@router.message(StateFilter(TripStates.distance))
async def trip_distance_step(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await message.answer("Записываю поездку. Отправьте километры, «-» — пропустить, или /cancel.")
        return

    if text in SKIP_TOKENS:
        distance = 0.0
    else:
        distance = parse_trip_distance(text)
        if distance is None:
            await message.answer(render_trip_invalid())
            return

    data = await state.get_data()
    await state.clear()
    await _log_trip(message, message.from_user.id, {"price": data["amount"], "distance_km": distance})
