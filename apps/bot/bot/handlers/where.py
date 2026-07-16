"""/where — «куда ехать?». Asks for the driver's location with a one-tap
reply-keyboard button (or the home district as a no-GPS fallback), then
renders the backend's stay/move recommendation. A bare location message —
sent without the /where prompt — goes through the same flow.
"""
from __future__ import annotations

import httpx
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)

from bot.api_client import api_client
from bot.config import settings
from bot.render import map_url, render_recommendation

router = Router(name="where")

HOME_CALLBACK = "where:home"


@router.message(Command("where"))
async def handle_where(message: Message) -> None:
    location_keyboard = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📍 Отправить местоположение", request_location=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Куда ехать? Отправьте местоположение кнопкой ниже — посчитаю лучший район.",
        reply_markup=location_keyboard,
    )
    await message.answer(
        "Или без геолокации:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🏠 По домашнему району", callback_data=HOME_CALLBACK)]
            ]
        ),
    )


@router.message(F.location)
async def handle_location(message: Message) -> None:
    """Any location message counts as a «куда ехать?» question, with or
    without the /where prompt before it."""
    await _send_recommendation(
        message, message.from_user.id, message.location.latitude, message.location.longitude
    )


@router.callback_query(F.data == HOME_CALLBACK)
async def handle_home_fallback(callback: CallbackQuery) -> None:
    await callback.answer()
    user = await api_client.link_telegram_user(callback.from_user.id)
    home_district_id = (user.get("driver_profile") or {}).get("home_district_id")
    if home_district_id is None:
        await callback.message.answer(
            "Домашний район не указан — задайте его командой /profile или отправьте геолокацию.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return

    districts = await api_client.get_districts()
    home = next((d for d in districts if d["id"] == home_district_id), None)
    if home is None:
        await callback.message.answer(
            "Не нашёл ваш домашний район — обновите его командой /profile.",
            reply_markup=ReplyKeyboardRemove(),
        )
        return
    await _send_recommendation(
        callback.message, callback.from_user.id, home["centroid_lat"], home["centroid_lng"]
    )


async def _send_recommendation(
    reply_target: Message, telegram_id: int, lat: float, lng: float
) -> None:
    user = await api_client.link_telegram_user(telegram_id)
    try:
        rec = await api_client.get_recommendation(user["id"], lat, lng)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400:
            # Backend couldn't geocode the point to a known district.
            await reply_target.answer(
                "Не удалось определить район по этой точке — похоже, она за пределами Москвы.",
                reply_markup=ReplyKeyboardRemove(),
            )
            return
        raise

    districts = await api_client.get_districts()
    district_names = {d["id"]: d["name"] for d in districts}
    # The one-tap location keyboard is one_time_keyboard, so it collapses on its
    # own; the recommendation carries the map deep link on an inline button
    # instead (a message can hold only one markup).
    await reply_target.answer(
        render_recommendation(rec, district_names),
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="🗺 Открыть на карте",
                        url=map_url(settings.web_base_url, rec.get("recommended_district_id")),
                    )
                ]
            ]
        ),
    )
