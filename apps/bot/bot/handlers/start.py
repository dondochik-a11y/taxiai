from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from bot.api_client import api_client

router = Router(name="start")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    await api_client.link_telegram_user(message.from_user.id)
    await message.answer(
        "Добро пожаловать в TaxiAI! Ваш аккаунт создан с настройками по умолчанию "
        "(тариф эконом, город Москва).\n\n"
        "Команда /profile — заполнить машину, расход топлива, аренду, домашний район "
        "и график смены прямо здесь, по шагам.\n\n"
        "Каждое утро я пришлю рекомендацию по лучшим часам для работы, предупрежу "
        "о всплеске спроса перед выездом и подведу итоги смены. Также можно просто "
        "написать мне вопрос — например, «где сейчас лучше работать?».\n\n"
        "Команда /link — связать этот чат с вашим аккаунтом в веб-приложении, "
        "чтобы профиль, финансы и история были общими."
    )
