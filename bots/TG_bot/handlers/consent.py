# bots/TG_bot/handlers/consent.py

from aiogram import Router, F
from aiogram.types import CallbackQuery
import asyncio

from app.users.crud import update_user_consent
from core.db.session import async_session_factory
from bots.TG_bot.keyboards.start_keyboard import start_keyboard
from bots.shared.utils import logger

router = Router()


@router.callback_query(F.data == "consent_yes")
async def handle_consent_yes(callback: CallbackQuery):
    telegram_id = str(callback.from_user.id)

    async with async_session_factory() as session:
        await update_user_consent(session, telegram_id, True)

    await callback.message.edit_text("Спасибо за согласие ✅")
    await callback.message.answer("Добро пожаловать!", reply_markup=start_keyboard())
    logger.info(f"[CONSENT] {telegram_id} дал согласие ✅")


@router.callback_query(F.data == "consent_no")
async def handle_consent_no(callback: CallbackQuery):
    await callback.message.edit_text("Вы не дали согласие ❌. Работа с ботом завершена.")
    await asyncio.sleep(2)
    await callback.message.answer("Если передумаете, просто нажмите /start.")
    logger.warning(f"[CONSENT] {callback.from_user.id} отказался ❌")
