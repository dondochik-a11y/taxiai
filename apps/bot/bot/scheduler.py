"""Polls the backend for due notifications and sends them. All decisioning
(what's due, dedup) happens server-side in
app/services/notification_service.py — this loop just renders + sends
whatever GET /v1/telegram/pending-notifications returns.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from bot.api_client import api_client
from bot.config import settings
from bot.render import map_url

logger = logging.getLogger("taxiai.bot.scheduler")


def _map_keyboard(district_id: int | None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🗺 Открыть карту",
                    url=map_url(settings.web_base_url, district_id),
                )
            ]
        ]
    )


async def notification_loop(bot: Bot) -> None:
    while True:
        try:
            notifications = await api_client.get_pending_notifications()
            for notif in notifications:
                # One bad row must not kill the whole batch.
                try:
                    telegram_id = notif.get("telegram_id")
                    if not telegram_id:
                        continue
                    await bot.send_message(
                        telegram_id,
                        notif["text"],
                        reply_markup=_map_keyboard(notif.get("district_id")),
                    )
                except Exception:
                    logger.exception("Failed to send notification %s", notif.get("type"))
        except Exception:
            logger.exception("Notification poll failed")
        await asyncio.sleep(settings.poll_interval_seconds)
