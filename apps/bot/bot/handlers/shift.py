"""/shift — start/stop the work shift. A single toggle: start if no shift is
open, otherwise stop the open one and show elapsed time + today's income.

The start/stop decision and the elapsed/income math all live server-side
(app/services/shift_service.py + finance_service.py); this handler only reads
the toggle result and renders it.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import render_shift_started, render_shift_stopped

router = Router(name="shift")


@router.message(Command("shift"))
async def handle_shift(message: Message) -> None:
    user = await api_client.link_telegram_user(message.from_user.id)
    result = await api_client.toggle_shift(user["id"])
    if result.get("action") == "started":
        await message.answer(render_shift_started(result.get("started_at")))
    else:
        await message.answer(render_shift_stopped(result))
