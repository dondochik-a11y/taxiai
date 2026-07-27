"""/goal — the driver's daily net-income target.

  /goal        → show the current goal + today's progress
  /goal 5000   → set the daily target (rubles, net)
  /goal off    → clear the goal

Parsing is pure (bot/render.parse_goal_arg); the target is stored on the driver
profile via PATCH /v1/users/{id}, and progress is read off the daily finance
summary (which carries the goal fields).
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import (
    parse_goal_arg,
    render_goal_cleared,
    render_goal_invalid,
    render_goal_progress,
    render_goal_set,
)

router = Router(name="goal")


@router.message(Command("goal"))
async def handle_goal(message: Message, command: CommandObject) -> None:
    parsed = parse_goal_arg(command.args)

    if parsed["action"] == "invalid":
        await message.answer(render_goal_invalid())
        return

    user = await api_client.link_telegram_user(message.from_user.id)

    if parsed["action"] == "show":
        summary = await api_client.get_finance_daily_summary(user["id"])
        await message.answer(render_goal_progress(summary))
        return

    if parsed["action"] == "clear":
        await api_client.update_profile(user["id"], {"daily_goal_income": None})
        await message.answer(render_goal_cleared())
        return

    # action == "set"
    amount = parsed["amount"]
    await api_client.update_profile(user["id"], {"daily_goal_income": amount})
    await message.answer(render_goal_set(amount))
