"""/finance — today's money summary, computed server-side by
app/services/finance_service.py; the bot only renders it."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import render_finance_summary

router = Router(name="finance")


@router.message(Command("finance"))
async def handle_finance(message: Message) -> None:
    user = await api_client.link_telegram_user(message.from_user.id)
    summary = await api_client.get_finance_daily_summary(user["id"])
    await message.answer(render_finance_summary(summary))
