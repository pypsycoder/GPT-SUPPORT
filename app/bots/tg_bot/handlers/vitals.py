# ============================================
# Telegram Bot: FSM-обработчики витальных показателей
# ============================================
# Конечные автоматы (FSM) для ввода АД, пульса и веса
# через Telegram-бота. Каждый показатель: выбор контекста
# измерения → ввод значения → сохранение в БД.

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bots.tg_bot.keyboards.inline import (
    vitals_menu_ikb,
    main_menu_ikb,
    bp_context_ikb,
    pulse_context_ikb,
    weight_context_ikb,
)
from app.users.crud import get_user_by_telegram_id, save_user
from app.vitals.models import BPMeasurement, PulseMeasurement, WeightMeasurement
from bots.shared.utils import logger

router = Router()

# ============================================
#   FSM States
# ============================================

class BPState(StatesGroup):
    choosing_context = State()
    waiting_for_value = State()

class PulseState(StatesGroup):
    choosing_context = State()
    waiting_for_value = State()

class WeightState(StatesGroup):
    choosing_context = State()
    waiting_for_value = State()


# ============================================
#   Helpers (парсинг и сохранение)
# ============================================

async def _get_or_create_user(message: Message, session: AsyncSession):
    """
    Получаем пользователя из БД по telegram_id.
    Если его нет — создаём.
    """
    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name

    user = await get_user_by_telegram_id(session, telegram_id=telegram_id)
    if user is None:
        user = await save_user(
            session,
            telegram_id=telegram_id,
            full_name=full_name,
        )
        await session.flush()

    await session.refresh(user)
    return user


def _parse_bp_value(text: str) -> Optional[Tuple[int, int]]:
    cleaned = text.strip().replace(",", ".")
    cleaned = " ".join(cleaned.split())

    if "/" in cleaned:
        parts = cleaned.split("/")
    else:
        parts = cleaned.split()

    if len(parts) != 2:
        return None

    try:
        systolic = int(parts[0])
        diastolic = int(parts[1])
    except ValueError:
        return None

    if not (50 <= systolic <= 260 and 30 <= diastolic <= 160):
        return None

    return systolic, diastolic


def _parse_int_value(text: str, min_val: int, max_val: int) -> Optional[int]:
    cleaned = text.strip()
    try:
        value = int(cleaned)
    except ValueError:
        return None

    if not (min_val <= value <= max_val):
        return None

    return value


def _parse_weight_value(text: str, min_val: float = 30.0, max_val: float = 200.0) -> Optional[float]:
    cleaned = text.strip().replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None

    if not (min_val <= value <= max_val):
        return None

    return value


async def _save_bp(session: AsyncSession, user_id: int, systolic: int, diastolic: int, context: str):
    measurement = BPMeasurement(
        user_id=user_id,
        systolic=systolic,
        diastolic=diastolic,
        measured_at=datetime.now(timezone.utc),
        context=context,
    )
    session.add(measurement)
    await session.commit()
    logger.info("[vitals][bp] measurement saved for user_id=%s context=%s", user_id, context)


async def _save_pulse(session: AsyncSession, user_id: int, bpm: int, context: str):
    measurement = PulseMeasurement(
        user_id=user_id,
        bpm=bpm,
        measured_at=datetime.now(timezone.utc),
        context=context,
    )
    session.add(measurement)
    await session.commit()
    logger.info("[vitals][pulse] measurement saved for user_id=%s context=%s", user_id, context)


async def _save_weight(session: AsyncSession, user_id: int, weight: float, context: str):
    measurement = WeightMeasurement(
        user_id=user_id,
        weight=weight,
        measured_at=datetime.now(timezone.utc),
        context=context,
    )
    session.add(measurement)
    await session.commit()
    logger.info("[vitals][weight] measurement saved for user_id=%s context=%s", user_id, context)


# ============================================
#   Handlers (callback + message)
# ============================================

@router.callback_query(F.data == "menu:vitals")
async def open_vitals_menu(callback: CallbackQuery):
    await callback.message.edit_text(
        "📊 Выберите показатель для ввода:",
        reply_markup=vitals_menu_ikb(),
    )
    await callback.answer()

# --- АД (BP) ---

@router.callback_query(F.data == "vitals:bp")
async def start_bp_flow(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BPState.choosing_context)
    await callback.message.edit_text(
        "💪 Давайте запишем давление.\n\nВыберите, где его измерили:",
        reply_markup=bp_context_ikb(),
    )
    await callback.answer()


@router.callback_query(BPState.choosing_context, F.data.regexp(r"^vitals:bp_ctx:"))
async def bp_context_chosen(callback: CallbackQuery, state: FSMContext):
    context_code = callback.data.split(":")[-1]
    await state.update_data(context=context_code)

    await state.set_state(BPState.waiting_for_value)
    await callback.message.edit_text(
        "💪 Теперь напишите давление в виде <b>120/80</b>.",
        reply_markup=None,
    )
    await callback.answer()


@router.message(BPState.waiting_for_value)
async def bp_value_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text:
        await message.answer("Не вижу цифр 😔\nНапишите давление в виде 120/80.")
        return

    parsed = _parse_bp_value(message.text)
    if parsed is None:
        await message.answer("Не получилось прочитать давление 😔\nПример: 120/80.")
        return

    systolic, diastolic = parsed
    data = await state.get_data()
    context = data.get("context", "na")

    user = await _get_or_create_user(message, session)
    await _save_bp(session, user.id, systolic, diastolic, context)
    await state.clear()

    await message.answer(
        f"Записал давление ✅\n<b>{systolic}/{diastolic} мм рт. ст.</b>",
        reply_markup=vitals_menu_ikb(),
    )

# --- Пульс ---

@router.callback_query(F.data == "vitals:pulse")
async def start_pulse_flow(callback: CallbackQuery, state: FSMContext):
    await state.set_state(PulseState.choosing_context)
    await callback.message.edit_text(
        "💓 Запишем пульс. Выберите контекст:",
        reply_markup=pulse_context_ikb(),
    )
    await callback.answer()


@router.callback_query(PulseState.choosing_context, F.data.regexp(r"^vitals:pulse_ctx:"))
async def pulse_context_chosen(callback: CallbackQuery, state: FSMContext):
    context_code = callback.data.split(":")[-1]
    await state.update_data(context=context_code)

    await state.set_state(PulseState.waiting_for_value)
    await callback.message.edit_text(
        "💓 Напишите пульс (только число, например 72).",
        reply_markup=None,
    )
    await callback.answer()


@router.message(PulseState.waiting_for_value)
async def pulse_value_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text:
        await message.answer("Не вижу цифр 😔\nНапишите пульс числом, например 72.")
        return

    bpm = _parse_int_value(message.text, min_val=30, max_val=220)
    if bpm is None:
        await message.answer("Пожалуйста, только число.\nПример: 60, 72, 90.")
        return

    data = await state.get_data()
    context = data.get("context", "na")

    user = await _get_or_create_user(message, session)
    await _save_pulse(session, user.id, bpm, context)
    await state.clear()

    await message.answer(
        f"Записал пульс ✅\n<b>{bpm} уд/мин</b>",
        reply_markup=vitals_menu_ikb(),
    )

# --- Вес ---

@router.callback_query(F.data == "vitals:weight")
async def start_weight_flow(callback: CallbackQuery, state: FSMContext):
    await state.set_state(WeightState.choosing_context)
    await callback.message.edit_text(
        "⚖️ Запишем вес.\nВыберите контекст:",
        reply_markup=weight_context_ikb(),
    )
    await callback.answer()


@router.callback_query(WeightState.choosing_context, F.data.regexp(r"^vitals:weight_ctx:"))
async def weight_context_chosen(callback: CallbackQuery, state: FSMContext):
    context_code = callback.data.split(":")[-1]
    await state.update_data(context=context_code)

    await state.set_state(WeightState.waiting_for_value)
    await callback.message.edit_text(
        "⚖️ Напишите вес в кг.\nМожно через точку или запятую.",
        reply_markup=None,
    )
    await callback.answer()


@router.message(WeightState.waiting_for_value)
async def weight_value_handler(message: Message, state: FSMContext, session: AsyncSession):
    if not message.text:
        await message.answer("Напишите вес в килограммах, например 70.5.")
        return

    weight = _parse_weight_value(message.text)
    if weight is None:
        await message.answer("Пожалуйста число, например 70, 70.5 или 70,5.")
        return

    data = await state.get_data()
    context = data.get("context", "na")

    user = await _get_or_create_user(message, session)
    await _save_weight(session, user.id, weight, context)
    await state.clear()

    await message.answer(
        f"Записал вес ✅\n<b>{weight:.1f} кг</b>",
        reply_markup=vitals_menu_ikb(),
    )
