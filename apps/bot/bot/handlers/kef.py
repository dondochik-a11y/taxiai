"""/kef — top districts by current surge coefficient. Each row is marked by
how real its number is (see KEF_SOURCE_LABELS in bot/render.py): the source
cascade lives server-side in app/services/surge_service.py.
"""
from __future__ import annotations

import asyncio

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import api_client
from bot.config import settings
from bot.render import map_url, render_kef_table

router = Router(name="kef")


@router.message(Command("kef"))
async def handle_kef(message: Message) -> None:
    surge_rows, districts = await asyncio.gather(
        api_client.get_current_surge(), api_client.get_districts()
    )
    district_names = {d["id"]: d["name"] for d in districts}
    top = max(surge_rows, key=lambda r: r["surge"], default=None)
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗺 Открыть карту",
                    url=map_url(settings.web_base_url, top["district_id"] if top else None),
                )
            ]
        ]
    )
    await message.answer(
        render_kef_table(surge_rows, district_names), parse_mode="HTML", reply_markup=keyboard
    )
