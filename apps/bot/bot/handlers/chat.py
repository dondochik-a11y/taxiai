from aiogram import Router
from aiogram.types import Message

from bot.api_client import api_client

router = Router(name="chat")


@router.message()
async def handle_free_text(message: Message) -> None:
    """Any non-command message is forwarded to the AI chat assistant — the
    bot itself has no NLU, the backend's LLMProvider.chat() does all the work."""
    if not message.text:
        return
    user = await api_client.link_telegram_user(message.from_user.id)
    reply = await api_client.send_chat_message(user["id"], message.text)
    await message.answer(reply)
