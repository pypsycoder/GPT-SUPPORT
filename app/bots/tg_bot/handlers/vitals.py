from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Tuple

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

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
from core.db.session import async_session_factory

router = Router()


# ---------- Состояния FSM ----------

class BPState(StatesGroup):
    # Ожидаем ввод давления
    choosing_context = State()
    waiting_for_value = State()


class PulseState(StatesGroup):
    # Ожидаем ввод пульса
    choosing_context = State()
    waiting_for_value = State()


class WeightState(StatesGroup):
    # Ожидаем ввод веса
    choosing_context = State()
    waiting_for_value = State()


# ---------- Вспомогательные функции ----------

# _get_or_create_user
async def _get_or_create_user(message: Message):
    """
    Получаем пользователя из БД по telegram_id.
    Если его нет — создаём.
    """
    telegram_id = str(message.from_user.id)
    full_name = message.from_user.full_name

    async with async_session_factory() as session:
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


# _parse_bp_value
def _parse_bp_value(text: str) -> Optional[Tuple[int, int]]:
    """
    Парсим давление из строки вида '120/80' или '120 80'.
    Возвращаем (systolic, diastolic) или None.
    """
    cleaned = text.strip().replace(",", ".")
    # Заменяем несколько пробелов на один
    cleaned = " ".join(cleaned.split())

    # Варианты: "120/80", "120 / 80", "120 80"
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

    # Простая санитарная проверка
    if not (50 <= systolic <= 260 and 30 <= diastolic <= 160):
        return None

    return systolic, diastolic


# _parse_int_value
def _parse_int_value(text: str, min_val: int, max_val: int) -> Optional[int]:
    """
    Парсим целое число в заданном диапазоне.
    """
    cleaned = text.strip()
    try:
        value = int(cleaned)
    except ValueError:
        return None

    if not (min_val <= value <= max_val):
        return None

    return value


# _parse_weight_value
def _parse_weight_value(text: str, min_val: float = 30.0, max_val: float = 200.0) -> Optional[float]:
    """
    Парсим вес: допускаем запятую или точку.
    """
    cleaned = text.strip().replace(",", ".")
    try:
        value = float(cleaned)
    except ValueError:
        return None

    if not (min_val <= value <= max_val):
        return None

    return value


# _save_bp
async def _save_bp(user_id: int, systolic: int, diastolic: int):
    """
    Сохраняем запись давления в БД.
    Пульс здесь не трогаем — он отдельно.
    """
    async with async_session_factory() as session:
        measurement = BPMeasurement(
            user_id=user_id,
            systolic=systolic,
            diastolic=diastolic,
            measured_at=datetime.now(timezone.utc),
        )
        session.add(measurement)
        await session.commit()
        logger.info("[vitals][bp] measurement saved for user_id=%s", user_id)


# _save_pulse
async def _save_pulse(user_id: int, bpm: int):
    """
    Сохраняем пульс в БД.
    """
    async with async_session_factory() as session:
        measurement = PulseMeasurement(
            user_id=user_id,
            bpm=bpm,
            measured_at=datetime.now(timezone.utc),
        )
        session.add(measurement)
        await session.commit()
        logger.info("[vitals][pulse] measurement saved for user_id=%s", user_id)


# _save_weight
async def _save_weight(user_id: int, weight: float):
    """
    Сохраняем вес в БД.
    """
    async with async_session_factory() as session:
        measurement = WeightMeasurement(
            user_id=user_id,
            weight=weight,
            measured_at=datetime.now(timezone.utc),
        )
        session.add(measurement)
        await session.commit()
        logger.info("[vitals][weight] measurement saved for user_id=%s", user_id)


# ---------- Хендлеры меню ----------

# open_vitals_menu
@router.callback_query(F.data == "menu:vitals")
async def open_vitals_menu(callback: CallbackQuery):
    """
    Открываем меню показателей.
    """
    await callback.message.edit_text(
        "📊 Выберите показатель для ввода:",
        reply_markup=vitals_menu_ikb(),
    )
    await callback.answer()


# ---------- Давление ----------

# start_bp_flow
@router.callback_query(F.data == "vitals:bp")
async def start_bp_flow(callback: CallbackQuery, state: FSMContext):
    """
    Старт ввода давления: сначала спрашиваем контекст.
    """
    await state.set_state(BPState.choosing_context)
    await callback.message.edit_text(
        "💪 Давайте запишем давление.\n\n"
        "Сначала выберите, где его измерили:",
        reply_markup=bp_context_ikb(),
    )
    await callback.answer()


@router.callback_query(BPState.choosing_context, F.data.regexp(r"^vitals:bp_ctx:"))
async def bp_context_chosen(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал контекст измерения давления.
    """
    # достаём код контекста из callback_data
    # vitals:bp_ctx:pre_hd → "pre_hd"
    context_code = callback.data.split(":")[-1] if callback.data else "na"

    # сохраняем в FSM, пока нигде не используем (на будущее для БД)
    await state.update_data(context=context_code)

    # переходим к вводу значения
    await state.set_state(BPState.waiting_for_value)
    await callback.message.edit_text(
        "💪 Теперь напишите давление.\n\n"
        "Формат: <b>120/80</b>\n"
        "Примеры:\n"
        "• <code>120/80</code>\n"
        "• <code>120 80</code>",
        reply_markup=None,
    )
    await callback.answer()

@router.message(BPState.waiting_for_value)
async def bp_value_handler(message: Message, state: FSMContext):
    """
    Принимаем и сохраняем давление.
    """
    if not message.text:
        await message.answer(
            "Не вижу цифр 😔\n\n"
            "Напишите, пожалуйста, давление в виде <b>120/80</b>."
        )
        return

    parsed = _parse_bp_value(message.text)
    if parsed is None:
        await message.answer(
            "Не получилось прочитать давление 😔\n\n"
            "Примеры:\n"
            "• <code>120/80</code>\n"
            "• <code>120 80</code>\n\n"
            "Попробуйте ещё раз."
        )
        return

    systolic, diastolic = parsed

    # достаём контекст из состояния (если он есть)
    data = await state.get_data()
    context = data.get("context", "na")


    user = await _get_or_create_user(message)
    await _save_bp(user_id=user.id, systolic=systolic, diastolic=diastolic)
    await state.clear()

    await message.answer(
        f"Записал давление ✅\n\n"
        f"<b>{systolic} / {diastolic} мм рт. ст.</b>\n\n"
        "Если хотите исправить — нажмите «💪 Давление» и отправьте новое значение.",
        reply_markup=vitals_menu_ikb(),
    )



# ---------- Пульс ----------

# start_pulse_flow
@router.callback_query(F.data == "vitals:pulse")
async def start_pulse_flow(callback: CallbackQuery, state: FSMContext):
    """
    Старт ввода пульса: сначала спрашиваем контекст.
    """
    await state.set_state(PulseState.choosing_context)
    await callback.message.edit_text(
        "💓 Давайте запишем пульс.\n\n"
        "Сначала выберите, где его измерили:",
        reply_markup=pulse_context_ikb(),
    )
    await callback.answer()

@router.callback_query(PulseState.choosing_context, F.data.regexp(r"^vitals:pulse_ctx:"))
async def pulse_context_chosen(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал контекст измерения пульса.
    """
    context_code = callback.data.split(":")[-1] if callback.data else "na"
    await state.update_data(context=context_code)

    await state.set_state(PulseState.waiting_for_value)
    await callback.message.edit_text(
        "💓 Теперь напишите пульс — сколько ударов в минуту.\n\n"
        "Пример: <code>72</code>",
        reply_markup=None,
    )
    await callback.answer()


# pulse_value_handler
@router.message(PulseState.waiting_for_value)
async def pulse_value_handler(message: Message, state: FSMContext):
    """
    Принимаем и сохраняем пульс.
    """
    if not message.text:
        await message.answer(
            "Не вижу цифр 😔\n\n"
            "Напишите, пожалуйста, пульс — только число.\n"
            "Пример: <code>72</code>"
        )
        return

    bpm = _parse_int_value(message.text, min_val=30, max_val=220)
    if bpm is None:
        await message.answer(
            "Не получилось прочитать пульс 😔\n\n"
            "Напишите, пожалуйста, только число.\n"
            "Примеры: <code>60</code>, <code>72</code>, <code>90</code>."
        )
        return

    data = await state.get_data()
    context = data.get("context", "na")  # пока не используем, но он уже есть

    user = await _get_or_create_user(message)
    await _save_pulse(user_id=user.id, bpm=bpm)
    await state.clear()

    await message.answer(
        f"Записал пульс ✅\n\n"
        f"<b>{bpm} ударов в минуту</b>\n\n"
        "Если хотите исправить — нажмите «💓 Пульс» и отправьте новое значение.",
        reply_markup=vitals_menu_ikb(),
    )


# ---------- Вес ----------

# start_weight_flow
@router.callback_query(F.data == "vitals:weight")
async def start_weight_flow(callback: CallbackQuery, state: FSMContext):
    """
    Старт ввода веса: сначала спрашиваем контекст.
    """
    await state.set_state(WeightState.choosing_context)
    await callback.message.edit_text(
        "⚖️ Давайте запишем вес.\n\n"
        "Сначала выберите, в каком контексте он измерен:",
        reply_markup=weight_context_ikb(),
    )
    await callback.answer()

@router.callback_query(WeightState.choosing_context, F.data.regexp(r"^vitals:weight_ctx:"))
async def weight_context_chosen(callback: CallbackQuery, state: FSMContext):
    """
    Пользователь выбрал контекст измерения веса.
    """
    context_code = callback.data.split(":")[-1]
    await state.update_data(context=context_code)

    await state.set_state(WeightState.waiting_for_value)
    await callback.message.edit_text(
        "⚖️ Теперь напишите вес в килограммах.\n\n"
        "Можно через точку или запятую.\n\n"
        "Примеры:\n"
        "• <code>70</code>\n"
        "• <code>70.5</code>\n"
        "• <code>70,5</code>",
        reply_markup=None,
    )
    await callback.answer()


@router.message(WeightState.waiting_for_value)
async def weight_value_handler(message: Message, state: FSMContext):
    """
    Принимаем и сохраняем вес.
    """
    if not message.text:
        await message.answer(
            "Не вижу цифр 😔\n\n"
            "Напишите, пожалуйста, вес в килограммах.\n"
            "Пример: <code>70</code> или <code>70.5</code>."
        )
        return

    weight = _parse_weight_value(message.text)
    if weight is None:
        await message.answer(
            "Не получилось прочитать вес 😔\n\n"
            "Напишите, пожалуйста, только число.\n"
            "Примеры: <code>70</code>, <code>70.5</code>, <code>70,5</code>."
        )
        return

    data = await state.get_data()
    context = data.get("context", "na")

    user = await _get_or_create_user(message)
    await _save_weight(user_id=user.id, weight=weight)  # context пока не сохраняем в БД
    await state.clear()

    await message.answer(
        f"Записал вес ✅\n\n"
        f"<b>{weight:.1f} кг</b>\n\n"
        "Если хотите исправить — нажмите «⚖️ Вес» и введите новое значение.",
        reply_markup=vitals_menu_ikb(),
    )
