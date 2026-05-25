"""Minimal questionnaire FSM compatibility layer for bot menus."""

from __future__ import annotations

from aiogram import Router
from aiogram.fsm.context import FSMContext

router = Router()


async def start_hads(message, state: FSMContext) -> None:
    """Legacy entrypoint used by the deprecated reply-menu router."""
    await state.clear()
    await message.answer("Опрос HADS скоро будет доступен из этого меню.")


async def start_hads_for_user(telegram_id: str, message, state: FSMContext) -> None:
    """Current entrypoint used by the inline-menu router."""
    del telegram_id
    await state.clear()
    await message.answer("Опрос HADS скоро будет доступен из этого меню.")
