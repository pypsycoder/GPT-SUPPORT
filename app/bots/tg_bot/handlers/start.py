from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message

from app.users.crud import get_user_by_telegram_id, save_user
from app.bots.tg_bot.keyboards.inline import main_menu_ikb
from app.bots.tg_bot.keyboards.consent_keyboard import consent_keyboard
from bots.shared.utils import logger

from core.db.session import async_session_factory

router = Router()


@router.message(CommandStart())
async def handle_start(message: Message):
    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name

    logger.info(f"[START] Пользователь {telegram_id} начал работу")

    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if not user:
            user = await save_user(session, telegram_id, full_name)
            await session.commit()

        if not user.consent_bot_use:
            await message.answer(
                "Перед началом работы необходимо дать согласие на обработку персональных данных "
                "и использование бота.",
                reply_markup=consent_keyboard()
            )
            return

    await message.answer("Главное меню:", reply_markup=main_menu_ikb())
    logger.info(f"[START] {telegram_id} уже зарегистрирован и дал согласие ✅")
