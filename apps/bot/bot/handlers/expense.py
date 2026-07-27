"""/expense — log a manual cost (wash / fine / other) so it reduces net income
in the real finance summary (office task #101).

  /expense              → pick a category, then enter the amount
  /expense wash 300     → inline
  /expense wash         → …category chosen, ask the amount

Fuel is intentionally not a category: the daily summary already estimates fuel
from distance, so a manual fuel receipt would double-count. Parsing/formatting
is pure (bot/render); this handler does the FSM plumbing + POST /v1/finance/expenses.
"""
from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from bot.api_client import api_client
from bot.render import (
    EXPENSE_LABELS,
    parse_expense,
    parse_expense_amount,
    render_expense_ask_amount,
    render_expense_invalid,
    render_expense_logged,
    render_expense_prompt,
)

router = Router(name="expense")


class ExpenseStates(StatesGroup):
    category = State()
    amount = State()


def _category_keyboard() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=label, callback_data=f"exp:{key}")]
        for key, label in EXPENSE_LABELS.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _log_expense(message: Message, telegram_id: int, category: str, amount: float) -> None:
    user = await api_client.link_telegram_user(telegram_id)
    expense = await api_client.create_expense(
        user["id"], {"category": category, "amount": amount}
    )
    await message.answer(render_expense_logged(expense))


@router.message(Command("expense"))
async def handle_expense(message: Message, command: CommandObject, state: FSMContext) -> None:
    parsed = parse_expense(command.args)

    if parsed["action"] == "invalid":
        await message.answer(render_expense_invalid())
        return

    if parsed["action"] == "log":
        await _log_expense(message, message.from_user.id, parsed["category"], parsed["amount"])
        return

    if parsed["action"] == "need_amount":
        await state.clear()
        await state.update_data(category=parsed["category"])
        await state.set_state(ExpenseStates.amount)
        await message.answer(render_expense_ask_amount(parsed["category"]))
        return

    # action == "prompt" → offer the category buttons.
    await state.clear()
    await state.set_state(ExpenseStates.category)
    await message.answer(render_expense_prompt(), reply_markup=_category_keyboard())


@router.message(Command("cancel"), StateFilter(ExpenseStates.category, ExpenseStates.amount))
async def cancel_expense(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Отменил запись расхода. /expense — начать заново.")


@router.callback_query(StateFilter(ExpenseStates.category))
async def expense_category_step(callback: CallbackQuery, state: FSMContext) -> None:
    _, category = (callback.data or "exp:other").split(":", 1)
    await state.update_data(category=category)
    await state.set_state(ExpenseStates.amount)
    await callback.answer()
    await callback.message.answer(render_expense_ask_amount(category))


@router.message(StateFilter(ExpenseStates.amount))
async def expense_amount_step(message: Message, state: FSMContext) -> None:
    text = (message.text or "").strip()
    if text.startswith("/"):
        await message.answer("Записываю расход. Отправьте сумму в ₽ или /cancel.")
        return
    amount = parse_expense_amount(text)
    if amount is None:
        await message.answer(render_expense_invalid())
        return
    data = await state.get_data()
    await state.clear()
    await _log_expense(message, message.from_user.id, data.get("category", "other"), amount)
