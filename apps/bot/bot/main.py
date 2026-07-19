from __future__ import annotations

import asyncio
import logging
from contextlib import suppress

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.base import BaseStorage
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from bot.api_client import api_client
from bot.config import settings
from bot.handlers import chat, errors, finance, help, kef, link, photo, plan, profile, start, where
from bot.scheduler import notification_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("taxiai.bot")

BOT_COMMANDS = [
    BotCommand(command="start", description="Начало работы"),
    BotCommand(command="where", description="Куда ехать сейчас"),
    BotCommand(command="kef", description="Кэф по районам"),
    BotCommand(command="finance", description="Итоги дня: доход и расходы"),
    BotCommand(command="plan", description="Лучшие часы для работы сегодня"),
    BotCommand(command="profile", description="Заполнить профиль водителя"),
    BotCommand(command="link", description="Связать с веб-приложением"),
    BotCommand(command="help", description="Что умеет бот"),
    BotCommand(command="cancel", description="Выйти из заполнения профиля"),
]


def _build_storage() -> BaseStorage:
    """Redis-backed FSM state when REDIS_URL is set (survives restarts, so a
    /profile wizard in progress isn't silently dropped); in-memory fallback
    for bare local runs."""
    if settings.redis_url:
        from aiogram.fsm.storage.redis import RedisStorage

        return RedisStorage.from_url(settings.redis_url)
    logger.warning("REDIS_URL is not set — FSM state is in-memory and is lost on restart.")
    return MemoryStorage()


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set — the bot cannot start without it.")

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher(storage=_build_storage())
    # Error events propagate to parent routers only, so the global handler
    # must live on the dispatcher itself to cover every router below.
    dispatcher.errors.register(errors.on_error)

    dispatcher.include_router(start.router)
    dispatcher.include_router(link.router)
    dispatcher.include_router(help.router)
    dispatcher.include_router(where.router)  # also catches bare location messages
    dispatcher.include_router(kef.router)
    dispatcher.include_router(finance.router)
    dispatcher.include_router(plan.router)
    dispatcher.include_router(profile.router)  # state-filtered; must come before the catch-all below
    dispatcher.include_router(photo.router)  # F.photo; the catch-all below would swallow photos
    dispatcher.include_router(chat.router)  # catch-all; must be registered last

    await bot.set_my_commands(BOT_COMMANDS)

    notify_task = asyncio.create_task(notification_loop(bot))
    logger.info("Bot starting, polling backend at %s", settings.api_base_url)
    try:
        await dispatcher.start_polling(bot)
    finally:
        notify_task.cancel()
        with suppress(asyncio.CancelledError):
            await notify_task
        await api_client.close()


if __name__ == "__main__":
    asyncio.run(main())
