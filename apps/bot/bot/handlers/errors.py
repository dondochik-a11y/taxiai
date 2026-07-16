"""Global error handler — registered on the Dispatcher itself (error events
propagate handler-router → parents, so a sibling router would never see
them). Logs the traceback and tells the user something went wrong instead of
staying silent."""
from __future__ import annotations

import logging

from aiogram.types import ErrorEvent

logger = logging.getLogger("taxiai.bot.errors")

ERROR_TEXT = "Что-то пошло не так, попробуйте ещё раз."


async def on_error(event: ErrorEvent) -> bool:
    logger.error("Update handling failed", exc_info=event.exception)

    message = event.update.message
    if message is None and event.update.callback_query is not None:
        message = event.update.callback_query.message
    if message is not None:
        try:
            await message.answer(ERROR_TEXT)
        except Exception:
            logger.exception("Could not notify the user about the error")
    return True
