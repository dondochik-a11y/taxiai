"""/plan — best hour-windows to work today. Server-side it is a historical
average by weekday (app/services/daily_plan_service.py), not a same-day
forecast — the rendered text says so honestly."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import render_daily_plan

router = Router(name="plan")


@router.message(Command("plan"))
async def handle_plan(message: Message) -> None:
    windows = await api_client.get_daily_plan()
    await message.answer(render_daily_plan(windows))
