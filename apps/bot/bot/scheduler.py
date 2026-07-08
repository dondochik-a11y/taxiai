"""Polls the backend for due notifications and sends them. All decisioning
(what's due, dedup) happens server-side in
app/services/notification_service.py — this loop just renders + sends
whatever GET /v1/telegram/pending-notifications returns.
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from bot.api_client import api_client
from bot.config import settings

logger = logging.getLogger("taxiai.bot.scheduler")


async def notification_loop(bot: Bot) -> None:
    while True:
        try:
            notifications = await api_client.get_pending_notifications()
            for notif in notifications:
                telegram_id = notif.get("telegram_id")
                if not telegram_id:
                    continue
                await bot.send_message(telegram_id, notif["text"])
        except Exception:
            logger.exception("Notification poll failed")
        await asyncio.sleep(settings.poll_interval_seconds)
