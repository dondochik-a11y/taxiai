"""/link — connect this Telegram account and a web account to one profile.

- `/link CODE`  → attach this Telegram to the web account that made CODE
  (web-first user: generated the code in the web app's Профиль).
- `/link` alone → show a code to type into the web app so the web adopts this
  bot account (bot-first user).
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message

from bot.api_client import api_client

router = Router(name="link")


@router.message(Command("link"))
async def handle_link(message: Message, command: CommandObject) -> None:
    code = (command.args or "").strip()

    if code:
        resp = await api_client.redeem_link_code_telegram(code.upper(), message.from_user.id)
        if resp.status_code == 200:
            await message.answer(
                "✅ Telegram привязан к вашему аккаунту. Профиль, финансы и история "
                "теперь общие с веб-приложением."
            )
        elif resp.status_code in (404, 410):
            detail = resp.json().get("detail", "Код не подошёл.")
            await message.answer(f"❌ {detail}")
        else:
            await message.answer("Не удалось привязать. Попробуйте ещё раз чуть позже.")
        return

    # No code given — issue one for this bot account so the web can adopt it.
    user = await api_client.link_telegram_user(message.from_user.id)
    result = await api_client.create_link_code(user["id"])
    await message.answer(
        f"Ваш код для входа в веб-приложении: <b>{result['code']}</b>\n\n"
        "Откройте веб-приложение → «Профиль» → «Уже есть аккаунт? Ввести код» и "
        "введите его. Код действует 15 минут.\n\n"
        "Если же вы, наоборот, хотите привязать Telegram к уже существующему "
        "веб-аккаунту — возьмите код в веб-приложении и отправьте его сюда: "
        "<code>/link КОД</code>.",
        parse_mode="HTML",
    )
