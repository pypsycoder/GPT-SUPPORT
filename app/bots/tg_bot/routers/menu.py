from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.tg_bot.keyboards.common import (
    main_menu_kb,
    back_home_kb,
    scales_menu_kb,
    profile_menu_kb,
    learning_menu_kb,
    diary_menu_kb,
)
from app.scales.fsm.questionnaire import start_hads

menu_router = Router()


@menu_router.message(F.text == "/menu_reply")
async def cmd_menu(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@menu_router.message(F.text == "🧪 Шкалы")
async def open_scales(message: types.Message):
    await message.answer("Шкалы:\n• HADS — тревога/депрессия\n(другие — скоро)", reply_markup=scales_menu_kb())


@menu_router.message(F.text == "👤 Профиль")
async def open_profile(message: types.Message):
    await message.answer("Профиль: согласия, мои данные, настройки.", reply_markup=profile_menu_kb())


@menu_router.message(F.text == "📚 Обучение")
async def open_learning(message: types.Message):
    await message.answer("Обучение: короткие уроки, медиа и ссылки.", reply_markup=learning_menu_kb())


@menu_router.message(F.text == "📒 Дневник")
async def open_diary(message: types.Message):
    await message.answer("Дневник показателей:", reply_markup=diary_menu_kb())


@menu_router.message(F.text == "❓ Помощь")
async def open_help(message: types.Message):
    await message.answer("Помощь: FAQ и контакты поддержки.", reply_markup=back_home_kb())


@menu_router.message(F.text == "HADS")
async def go_hads(message: types.Message, state: FSMContext):
    await message.answer("Открываю HADS… (подключим FSM)", reply_markup=back_home_kb())
    await start_hads(message, state)


@menu_router.message(F.text == "Согласие")
async def profile_consent(message: types.Message, session: AsyncSession):
    await message.answer("Статус согласий: (покажем из БД) ✅/❌", reply_markup=back_home_kb())


@menu_router.message(F.text == "Мои данные")
async def profile_data(message: types.Message, session: AsyncSession):
    await message.answer("Мои данные: ФИО, дата рождения, часовой пояс…", reply_markup=back_home_kb())


@menu_router.message(F.text == "Настройки")
async def profile_settings(message: types.Message):
    await message.answer("Настройки: язык, уведомления, формат времени…", reply_markup=back_home_kb())


@menu_router.message(F.text == "Нефрология")
async def learning_neph(message: types.Message):
    await message.answer("Уроки по нефрологии (в разработке).", reply_markup=back_home_kb())


@menu_router.message(F.text == "Психология")
async def learning_psy(message: types.Message):
    await message.answer("Уроки по психологии (в разработке).", reply_markup=back_home_kb())


@menu_router.message(F.text == "➕ Ввести пульс")
async def diary_add_pulse(message: types.Message):
    await message.answer("Введите пульс (уд/мин), например: 78", reply_markup=back_home_kb())


@menu_router.message(F.text == "📈 Статистика 7 дней")
async def diary_stats(message: types.Message, session: AsyncSession):
    await message.answer("Статистика за 7 дней: min/max/avg (скоро).", reply_markup=back_home_kb())


@menu_router.message(F.text == "⬅️ Назад")
async def nav_back(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu_kb())


@menu_router.message(F.text == "🏠 Меню")
async def nav_home(message: types.Message):
    await message.answer("Главное меню:", reply_markup=main_menu_kb())
