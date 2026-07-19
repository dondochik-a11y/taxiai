"""Photo → crowdsourced kef: the driver drops a screenshot of the surge map
(Яндекс Про or the radar), the backend's vision OCR reads the bubbles and
stores them in kef_observations — the same pool the radar sweeps feed
(POST /v1/kef/ocr-ingest). The bot echoes what was read so a misread is
visible immediately.
"""
from __future__ import annotations

import base64
import logging

import httpx
from aiogram import Bot, F, Router
from aiogram.types import Message

from bot.api_client import api_client
from bot.render import render_ocr_result

router = Router(name="photo")
logger = logging.getLogger("taxiai.bot.photo")


@router.message(F.photo)
async def handle_photo(message: Message, bot: Bot) -> None:
    note = await message.answer("📷 Читаю кэф со скрина…")

    photo = message.photo[-1]  # renditions are sorted by size; take the largest
    file = await bot.get_file(photo.file_id)
    buffer = await bot.download_file(file.file_path)
    image_b64 = base64.b64encode(buffer.read()).decode()

    try:
        user = await api_client.get_user_by_telegram_id(message.from_user.id)
        result = await api_client.ocr_ingest_kef(image_b64, user_id=user.get("id") if user else None)
    except httpx.HTTPStatusError as exc:
        logger.warning("ocr-ingest failed: %s", exc)
        if exc.response.status_code == 503:
            text = "Распознавание скринов пока не включено на сервере — загляните позже."
        else:
            text = (
                "Не получилось прочитать кэф с этого скрина. Нужен скрин карты "
                "повышенного спроса с цифрами коэффициентов."
            )
        await note.edit_text(text)
        return
    except httpx.HTTPError as exc:
        logger.warning("ocr-ingest unreachable: %s", exc)
        await note.edit_text("Сервер сейчас недоступен — попробуйте прислать скрин позже.")
        return

    districts = await api_client.get_districts()
    district_names = {d["id"]: d["name"] for d in districts}
    await note.edit_text(render_ocr_result(result, district_names))
