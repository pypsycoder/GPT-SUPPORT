# ============================================
# Telegram Bot: Inline-меню бота
# ============================================
# Главное меню на inline-кнопках: обработка /menu,
# переходы между разделами, единственный источник правды для меню.

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession
from app.scales.fsm.questionnaire import start_hads_for_user

from app.bots.tg_bot.keyboards.inline import (
    main_menu_ikb,
    back_home_ikb,
    scales_menu_ikb,
    profile_menu_ikb,
    learning_menu_ikb,
    vitals_menu_ikb,
)
from app.scales.fsm.questionnaire import start_hads

menu_router = Router()


@menu_router.message(F.text == "/menu")
async def cmd_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu_ikb())


@menu_router.callback_query(F.data == "menu:scales")
async def open_scales(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Шкалы:\n• HADS — тревога/депрессия\n(другие — скоро)",
        reply_markup=scales_menu_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "menu:profile")
async def open_profile(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Профиль: согласия, мои данные, настройки.",
        reply_markup=profile_menu_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "menu:learning")
async def open_learning(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Обучение: короткие уроки, медиа и ссылки.",
        reply_markup=learning_menu_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "menu:vitals")
async def open_diary(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Дневник показателей:",
        reply_markup=vitals_menu_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "menu:help")
async def open_help(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Помощь:\n• /start — начать\n• /menu — главное меню\n• Вопросы — здесь.",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "scales:hads")
async def go_hads(cb: types.CallbackQuery, state: FSMContext):
    # закрываем "часики" на кнопке
    await cb.answer()
    # ВАЖНО: берем ID пользователя, а не бота
    telegram_id = str(cb.from_user.id)
    # запускаем общий хелпер FSM
    await start_hads_for_user(telegram_id, cb.message, state)


@menu_router.callback_query(F.data == "profile:consent")
async def profile_consent(cb: types.CallbackQuery, session: AsyncSession):
    await cb.message.edit_text(
        "Статус согласий: (прочтём из БД) ✅/❌",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "profile:data")
async def profile_data(cb: types.CallbackQuery, session: AsyncSession):
    await cb.message.edit_text(
        "Мои данные: ФИО, дата рождения, часовой пояс…",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "profile:settings")
async def profile_settings(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Настройки: язык, уведомления, формат времени…",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "learn:neph")
async def learning_neph(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Уроки по нефрологии (в разработке).",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "learn:psy")
async def learning_psy(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Уроки по психологии (в разработке).",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "diary:add_pulse")
async def diary_add_pulse(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Введите пульс (уд/мин), например: 78",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "diary:stats")
async def diary_stats(cb: types.CallbackQuery, session: AsyncSession):
    await cb.message.edit_text(
        "Статистика за 7 дней: min/max/avg (скоро).",
        reply_markup=back_home_ikb(),
    )
    await cb.answer()


@menu_router.callback_query(F.data == "nav:back")
async def nav_back(cb: types.CallbackQuery):
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu_ikb())
    await cb.answer()


@menu_router.callback_query(F.data == "nav:home")
async def nav_home(cb: types.CallbackQuery):
    await cb.message.edit_text("Главное меню:", reply_markup=main_menu_ikb())
    await cb.answer()
