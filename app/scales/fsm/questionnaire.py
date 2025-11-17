# questionnaire.py — универсальный FSM для шкал

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from app.scales.crud import (
    get_or_create_draft,
    update_draft_answer,
    delete_draft,
    finalize_response,
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
    from core.db.session import async_session_factory

    async with async_session_factory() as session:
        user = await get_user_by_telegram_id(session, telegram_id)

        if not user or not user.consent_bot_use:
            await message.answer(
                "⚠️ Чтобы пройти шкалу, нужно сначала пройти регистрацию через /start и дать согласие."
            )
            return

        schema = hads_schema
        draft = await get_or_create_draft(
            user.id,
            schema["code"],
            schema["version"],
            session,
        )
        current_index = draft["current_index"]
        answers = draft["answers"]

    # выставляем состояние и сохраняем данные в FSM
    await state.set_state(QuestionnaireFSM.answering)
    await state.update_data(
        schema=schema,
        current=current_index,
        answers=answers,
        user_id=user.id,
        draft_id=draft["id"],
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

    item = schema["items"][current]
    selected_value = int(callback.data)
    answers[item["id"]] = selected_value

    # сохраняем ответ в черновик
    await update_draft_answer(draft_id, item["id"], selected_value)

    # есть ещё вопросы — идём дальше
    if current + 1 < len(schema["items"]):
        next_item = schema["items"][current + 1]
        await state.update_data(current=current + 1, answers=answers)

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
        # Завершение: сохраняем в БД
        await finalize_response(user_id, schema, answers)
        await delete_draft(draft_id)

        # 🧮 Считаем баллы по подшкалам (A — тревога, D — депрессия)
        scores: dict[str, int] = {}
        for q_item in schema["items"]:
            item_id = q_item["id"]
            scale_code = q_item.get("scale")  # "A" или "D"
            if not scale_code:
                continue
            value = answers.get(item_id)
            if value is None:
                continue
            scores[scale_code] = scores.get(scale_code, 0) + int(value)

        # 🧾 Готовим человекочитаемую интерпретацию
        lines: list[str] = []
        output_cfg = schema.get("output", {})

        for scale_code, total in scores.items():
            cfg = output_cfg.get(scale_code)
            if not cfg:
                continue

            name = cfg.get("name", scale_code)
            cutoffs = cfg.get("cutoffs", [])
            labels = cfg.get("interpretation", [])

            # По умолчанию: одна граница -> 2 категории, две границы -> 3
            if len(cutoffs) == 2 and len(labels) >= 3:
                if total < cutoffs[0]:
                    level = labels[0]
                elif total < cutoffs[1]:
                    level = labels[1]
                else:
                    level = labels[2]
            elif len(cutoffs) == 1 and len(labels) >= 2:
                if total < cutoffs[0]:
                    level = labels[0]
                else:
                    level = labels[1]
            else:
                # fallback, если вдруг что-то изменится в схеме
                level = labels[0] if labels else "без интерпретации"

            lines.append(f"{name}: {total} баллов — {level}")

        result_text = "✅ Спасибо! Шкала завершена."

        if lines:
            result_text += "\n\nРезультаты:\n" + "\n".join(lines)

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
