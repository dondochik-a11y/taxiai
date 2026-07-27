"""/health — operator readout of demand-model freshness + forecast quality.
Thin adapter: the backend computes everything (GET /v1/health/model); the bot
only renders it. Handy for spotting a silently-stalled weekly retrain without
SSHing into the box."""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import render_model_health

router = Router(name="health")


@router.message(Command("health"))
async def handle_health(message: Message) -> None:
    health = await api_client.get_model_health()
    await message.answer(render_model_health(health), parse_mode="HTML")
