"""/alert — configure the proactive «рядом скачок спроса» push: the bot pings
you when your home district (or a neighbour) is surging RIGHT NOW.

  /alert       → show current on/off state + threshold
  /alert 1.7   → set the kef threshold and turn alerts on
  /alert off   → turn alerts off
  /alert on    → turn alerts on (keep the current threshold)

All decisioning (which districts count as "nearby", cooldown, real-data gate)
lives server-side in app/services/alerts.py + notification_service.py; this
handler only reads the arg and writes the two profile settings.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import parse_alert_arg, render_alert_status

router = Router(name="alert")

_DEFAULT_THRESHOLD = 1.5


def _current(profile: dict) -> tuple[bool, float]:
    enabled = bool(profile.get("surge_alert_enabled", False))
    threshold = float(profile.get("surge_alert_threshold") or _DEFAULT_THRESHOLD)
    return enabled, threshold


@router.message(Command("alert"))
async def handle_alert(message: Message, command: CommandObject) -> None:
    parsed = parse_alert_arg(command.args)
    if parsed["action"] == "invalid":
        await message.answer(
            "Не понял. Формат: «/alert 1.7» — задать порог кэфа, "
            "«/alert off» — выключить, «/alert on» — включить."
        )
        return

    user = await api_client.link_telegram_user(message.from_user.id)
    profile = user.get("driver_profile") or {}
    enabled, threshold = _current(profile)

    if parsed["action"] == "show":
        await message.answer(render_alert_status(enabled, threshold))
        return

    if parsed["action"] == "off":
        await api_client.update_profile(user["id"], {"surge_alert_enabled": False})
        await message.answer(render_alert_status(False, threshold))
        return

    if parsed["action"] == "on":
        await api_client.update_profile(user["id"], {"surge_alert_enabled": True})
        await message.answer(render_alert_status(True, threshold))
        return

    # action == "set"
    threshold = parsed["threshold"]
    await api_client.update_profile(
        user["id"], {"surge_alert_enabled": True, "surge_alert_threshold": threshold}
    )
    await message.answer(render_alert_status(True, threshold))
