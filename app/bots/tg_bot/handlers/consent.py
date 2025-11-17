from aiogram import Router, F
from aiogram.types import CallbackQuery
import asyncio

from app.users.crud import grant_user_consent
from core.db.session import async_session_factory
from app.bots.tg_bot.keyboards.inline import main_menu_ikb
from app.bots.tg_bot.keyboards.reply_start import reply_start_keyboard
from bots.shared.utils import logger

router = Router()


@router.callback_query(F.data == "consent_yes")
async def handle_consent_yes(callback: CallbackQuery):
    telegram_id = str(callback.from_user.id)

    async with async_session_factory() as session:
        await grant_user_consent(session, telegram_id)

    await callback.message.edit_text("Спасибо за согласие ✅")
    await callback.message.answer("Главное меню:", reply_markup=main_menu_ikb())
    await callback.message.answer(
        "Быстрые действия:",
        reply_markup=reply_start_keyboard(),
    )
    logger.info(f"[CONSENT] {telegram_id} дал согласие ✅")


@router.callback_query(F.data == "consent_no")
async def handle_consent_no(callback: CallbackQuery):
    await callback.message.edit_text("Вы не дали согласие ❌. Работа с ботом завершена.")
    await asyncio.sleep(2)
    await callback.message.answer("Если передумаете, просто нажмите /start.")
    logger.warning(f"[CONSENT] {callback.from_user.id} отказался ❌")
