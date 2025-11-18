# questionnaire.py — универсальный FSM для шкал

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from core.db.session import async_session_factory
from app.scales.engine.questionnaire_service import (
    build_result,
    process_answer,
    start_questionnaire_for_user,
)
from app.users.crud import get_user_by_telegram_id
from bots.shared.utils import logger

router = Router()


class QuestionnaireFSM(StatesGroup):
    # состояние, когда пользователь отвечает на вопросы шкалы
    answering = State()


# # построение клавиатуры
def build_options_keyboard(options: list[dict]) -> InlineKeyboardMarkup:
    """
    Собирает inline-клавиатуру из списка опций вида:
    {"text": str, "value": int}
    """
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=o["text"], callback_data=str(o["value"]))]
            for o in options
        ]
    )


# # старт HADS по текстовому сообщению
@router.message(F.text.lower() == "📝 пройти шкалу hads")
async def start_hads(message: Message, state: FSMContext) -> None:
    """
    Триггер для HADS, когда пользователь пишет/нажимает
    текст '📝 пройти шкалу HADS'.
    """
    telegram_id = str(message.from_user.id)
    await start_hads_for_user(telegram_id, message, state)


# # общий хелпер запуска HADS по telegram_id
async def start_hads_for_user(
    telegram_id: str,
    message: Message,
    state: FSMContext,
) -> None:
    """
    Общий запуск шкалы HADS:
    - находит пользователя по telegram_id
    - проверяет согласие на использование бота
    - поднимает/создаёт черновик
    - ставит FSM в состояние answering
    - показывает текущий вопрос

    Используется:
    - из текстового хендлера start_hads
    - из inline-меню (через callback, где есть cb.from_user.id)
    """
    from app.scales.schemas.hads import hads_schema
    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if not user or not user.consent_bot_use:
            await message.answer(
                "⚠️ Чтобы пройти шкалу, нужно сначала пройти регистрацию через /start и дать согласие."
            )
            return

        schema = hads_schema
        engine_data = await start_questionnaire_for_user(session, user, schema)
        current_index = engine_data["current_index"]
        answers = engine_data["answers"]

    # выставляем состояние и сохраняем данные в FSM
    await state.set_state(QuestionnaireFSM.answering)
    await state.update_data(
        schema=schema,
        current=current_index,
        answers=answers,
        user_id=user.id,
        draft_id=engine_data["draft_id"],
    )

    # показываем первый/текущий вопрос (как отдельное новое сообщение)
    await show_question(message, schema["items"][current_index])


# # показать вопрос (для первого вопроса и fallback-сценариев)
async def show_question(message: Message, item: dict) -> None:
    """
    Показывает один вопрос шкалы с вариантами ответов
    как отдельное сообщение бота.
    """
    await message.answer(
        text=item["text"],
        reply_markup=build_options_keyboard(item["options"]),
    )


# # обработка ответа
@router.callback_query(QuestionnaireFSM.answering, F.data)
async def handle_answer(callback: CallbackQuery, state: FSMContext) -> None:
    """
    Обрабатывает клик по варианту ответа:
    - сохраняет ответ в черновик
    - двигает индекс вперёд
    - показывает следующий вопрос в том же сообщении (edit_text)
      или завершает шкалу
    """
    data = await state.get_data()
    schema = data["schema"]
    current = data["current"]
    answers = data["answers"]
    user_id = data["user_id"]
    draft_id = data["draft_id"]

    selected_value = int(callback.data)

    async with async_session_factory() as session:
        engine_result = await process_answer(
            session,
            draft_id=draft_id,
            user_id=user_id,
            schema=schema,
            answers=answers,
            current_index=current,
            selected_value=selected_value,
        )

    if not engine_result.get("finished"):
        next_item = engine_result["next_item"]
        next_index = engine_result["next_index"]
        updated_answers = engine_result["answers"]

        await state.update_data(current=next_index, answers=updated_answers)

        # 🧩 Пытаемся показать следующий вопрос в том же сообщении (edit_text)
        try:
            await callback.message.edit_text(
                text=next_item["text"],
                reply_markup=build_options_keyboard(next_item["options"]),
            )
        except Exception as e:
            # fallback: если редактирование не удалось — шлём новый вопрос
            logger.warning(
                f"[Questionnaire] Не удалось отредактировать сообщение с вопросом, "
                f"отправляем новое. Ошибка: {e}"
            )
            await show_question(callback.message, next_item)
    else:
        final_answers = engine_result.get("answers", answers)
        result_payload = build_result(schema, final_answers)

        result_text = "✅ Спасибо! Шкала завершена."

        if result_payload["lines"]:
            result_text += "\n\nРезультаты:\n" + "\n".join(result_payload["lines"])

        # 🔘 Кнопки навигации (назад / меню)
        finish_kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="⬅️ Назад", callback_data="nav:back"),
                    InlineKeyboardButton(text="🏠 Меню", callback_data="nav:home"),
                ]
            ]
        )

        await callback.message.answer(
            result_text,
            reply_markup=finish_kb,
        )
        logger.info(f"[HADS] {user_id} завершил прохождение")
        await state.clear()
