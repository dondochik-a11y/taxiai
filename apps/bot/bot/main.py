from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.config import settings
from bot.handlers import chat, link, profile, start
from bot.scheduler import notification_loop

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("taxiai.bot")


async def main() -> None:
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set — the bot cannot start without it.")

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(start.router)
    dispatcher.include_router(link.router)  # /link command; before the catch-all
    dispatcher.include_router(profile.router)  # state-filtered; must come before the catch-all below
    dispatcher.include_router(chat.router)  # catch-all; must be registered last

    asyncio.create_task(notification_loop(bot))
    logger.info("Bot starting, polling backend at %s", settings.api_base_url)
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
