"""
Morning Service — утреннее проактивное сообщение на основе шаблона.

Архитектура:
  - GigaChat НЕ используется для генерации утреннего сообщения.
  - Чистый Python собирает контекст и подставляет его в шаблон.
  - GigaChat подключается только если пациент ответил (обычный chat flow).

Реальная схема БД:
  llm.chat_messages
    role, content, buttons_json (JSONB), request_type='morning'
  llm.patient_daily_context
    patient_id, context_date, context_json, message_sent, message_id
  dialysis_schedules (public)
    weekdays ARRAY[int] (ISO 1=Пн..7=Вс), valid_to IS NULL = активное
  medications.medication_prescriptions
    intake_schedule JSONB ['morning','afternoon','evening'], status='active'
  medications.medication_intakes
    intake_slot ('morning'/'afternoon'/'evening'), intake_datetime, patient_id
  sleep.sleep_records
    patient_id, sleep_date DATE
  vitals.bp_measurements
    user_id (=patient_id), measured_at DATETIME
  patient_streaks (public)
    patient_id, tracker, current_streak, best_streak
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import ChatMessage

logger = logging.getLogger("gpt-support-llm.morning")

# ---------------------------------------------------------------------------
# Шаблоны
# ---------------------------------------------------------------------------

_GREETINGS = {
    "morning": "Доброе утро.",
    "day":     "Добрый день.",
    "evening": "Добрый вечер.",
}


def _time_of_day(now: datetime) -> str:
    h = now.hour
    if h < 12:
        return "morning"
    if h < 17:
        return "day"
    return "evening"


# ---------------------------------------------------------------------------
# Сбор контекста
# ---------------------------------------------------------------------------


async def build_daily_context(
    patient_id: int,
    target_date: date,
    session: AsyncSession,
) -> dict:
    """
    Собирает контекст дня для одного пациента.
    Возвращает dict, пригодный для JSON-сериализации.
    """
    yesterday = target_date - timedelta(days=1)
    today_weekday = target_date.isoweekday()  # 1=Пн..7=Вс (совпадает с weekdays в dialysis_schedules)

    # 1. Диализ сегодня
    dialysis_row = await session.execute(
        text("""
            SELECT EXISTS(
                SELECT 1 FROM dialysis_schedules
                WHERE patient_id = :pid
                  AND valid_to IS NULL
                  AND :wd = ANY(weekdays)
            )
        """),
        {"pid": patient_id, "wd": today_weekday},
    )
    dialysis_today: bool = bool(dialysis_row.scalar())

    # 2. Активные назначения с утренним слотом
    total_row = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM medications.medication_prescriptions
            WHERE patient_id = :pid
              AND status = 'active'
              AND intake_schedule @> '["morning"]'::jsonb
              AND start_date <= :d
              AND (end_date IS NULL OR end_date >= :d)
        """),
        {"pid": patient_id, "d": target_date},
    )
    morning_meds_total: int = int(total_row.scalar() or 0)

    # 3. Сколько утренних приёмов уже отмечено сегодня
    done_row = await session.execute(
        text("""
            SELECT COUNT(DISTINCT prescription_id)
            FROM medications.medication_intakes
            WHERE patient_id = :pid
              AND intake_slot = 'morning'
              AND DATE(intake_datetime) = :d
        """),
        {"pid": patient_id, "d": target_date},
    )
    morning_meds_done: int = int(done_row.scalar() or 0)

    # 4. Пропуски вчера
    missed_yesterday: list[str] = []

    sleep_row = await session.execute(
        text("""
            SELECT EXISTS(
                SELECT 1 FROM sleep.sleep_records
                WHERE patient_id = :pid AND sleep_date = :d
            )
        """),
        {"pid": patient_id, "d": yesterday},
    )
    if not bool(sleep_row.scalar()):
        missed_yesterday.append("сон")

    vitals_row = await session.execute(
        text("""
            SELECT EXISTS(
                SELECT 1 FROM vitals.bp_measurements
                WHERE user_id = :uid AND DATE(measured_at) = :d
            )
        """),
        {"uid": patient_id, "d": yesterday},
    )
    if not bool(vitals_row.scalar()):
        missed_yesterday.append("показатели")

    if morning_meds_total > 0:
        meds_row = await session.execute(
            text("""
                SELECT EXISTS(
                    SELECT 1 FROM medications.medication_intakes
                    WHERE patient_id = :pid
                      AND DATE(intake_datetime) = :d
                )
            """),
            {"pid": patient_id, "d": yesterday},
        )
        if not bool(meds_row.scalar()):
            missed_yesterday.append("лекарства")

    missed_yesterday = missed_yesterday[:2]

    # 5. Серия лекарств
    streak_row = await session.execute(
        text("""
            SELECT current_streak, best_streak
            FROM patient_streaks
            WHERE patient_id = :pid AND tracker = 'medications'
        """),
        {"pid": patient_id},
    )
    streak_data = streak_row.fetchone()
    streak_medications: int = int(streak_data[0]) if streak_data else 0
    streak_best: int = int(streak_data[1]) if streak_data else 0

    return {
        "time_of_day": _time_of_day(datetime.now()),
        "dialysis_today": dialysis_today,
        "morning_meds_total": morning_meds_total,
        "morning_meds_done": morning_meds_done,
        "morning_meds_pending": max(0, morning_meds_total - morning_meds_done),
        "missed_yesterday": missed_yesterday,
        "streak_medications": streak_medications,
        "streak_best": streak_best,
    }


# ---------------------------------------------------------------------------
# Формирование шаблона
# ---------------------------------------------------------------------------


def build_morning_message(ctx: dict) -> dict:
    """
    Формирует текст и кнопки утреннего сообщения по шаблону (без LLM).
    Возвращает {"text": str, "buttons": list[dict]}.
    """
    lines: list[str] = []
    buttons: list[dict] = []
    blocks_used = 0

    lines.append(_GREETINGS[ctx["time_of_day"]])

    if ctx["dialysis_today"]:
        lines.append("Сегодня день диализа.")
        blocks_used += 1

    if ctx["morning_meds_pending"] > 0:
        if ctx["time_of_day"] == "morning":
            lines.append("Утренние лекарства ещё не отмечены.")
        else:
            lines.append(
                "Утренние лекарства не отмечены — "
                "если принимали, можно внести сейчас."
            )
        buttons.append({"label": "💊 Отметить", "action": "open_medications"})
        buttons.append({"label": "Позже",       "action": "dismiss_morning"})
        blocks_used += 1

    elif ctx["missed_yesterday"] and blocks_used < 2:
        missed_str = " и ".join(ctx["missed_yesterday"])
        lines.append(f"Вчера не было записей: {missed_str}.")
        buttons.append({"label": "Внести сейчас", "action": "open_trackers"})
        blocks_used += 1

    elif ctx["streak_medications"] >= 3 and not ctx["missed_yesterday"]:
        s = ctx["streak_medications"]
        if s == ctx["streak_best"] and s >= 7:
            lines.append(f"Вы уже {s} дней подряд отмечаете лекарства — это ваш рекорд.")
        else:
            lines.append(f"Вы уже {s} дней подряд отмечаете лекарства.")
        blocks_used += 1

    if blocks_used == 0:
        lines.append("Вчера вы всё отметили — так держать.")

    return {
        "text": "\n".join(lines),
        "buttons": buttons,
    }


# ---------------------------------------------------------------------------
# Вспомогательные функции работы с patient_daily_context
# ---------------------------------------------------------------------------


async def _is_morning_sent_today(
    patient_id: int,
    context_date: date,
    session: AsyncSession,
) -> bool:
    row = await session.execute(
        text("""
            SELECT message_sent
            FROM llm.patient_daily_context
            WHERE patient_id = :pid AND context_date = :d
        """),
        {"pid": patient_id, "d": context_date},
    )
    rec = row.fetchone()
    return bool(rec and rec[0])


async def _upsert_daily_context(
    patient_id: int,
    context_date: date,
    ctx: dict,
    message_id: int,
    session: AsyncSession,
) -> None:
    await session.execute(
        text("""
            INSERT INTO llm.patient_daily_context
                (patient_id, context_date, context_json, message_sent, message_id)
            VALUES (:pid, :d, CAST(:ctx AS jsonb), TRUE, :mid)
            ON CONFLICT (patient_id, context_date) DO UPDATE
                SET context_json  = CAST(:ctx AS jsonb),
                    message_sent  = TRUE,
                    message_id    = :mid
        """),
        {
            "pid": patient_id,
            "d":   context_date,
            "ctx": json.dumps(ctx, ensure_ascii=False, default=str),
            "mid": message_id,
        },
    )


# ---------------------------------------------------------------------------
# Публичные функции
# ---------------------------------------------------------------------------


async def ensure_morning_message(patient_id: int, session: AsyncSession) -> None:
    """
    Вызывается при открытии чата (GET /api/chat/history/{patient_id}).

    Если пациент открыл чат после 06:00 и утреннего сообщения ещё нет —
    генерирует и сохраняет его на лету.
    Повторный вызов в тот же день ничего не делает.
    """
    now = datetime.now()
    if now.hour < 6:
        return

    today = date.today()
    if await _is_morning_sent_today(patient_id, today, session):
        return

    try:
        ctx = await build_daily_context(patient_id, today, session)
        msg = build_morning_message(ctx)
    except Exception as exc:
        logger.error("[morning] build_daily_context failed patient=%d: %s", patient_id, exc)
        return

    chat_msg = ChatMessage(
        patient_id=patient_id,
        role="assistant",
        content=msg["text"],
        tokens_used=0,
        model_used=None,
        domain="routine",
        request_type="morning",
        is_read=False,
        buttons_json=msg["buttons"] if msg["buttons"] else None,
    )
    session.add(chat_msg)
    await session.flush()

    await _upsert_daily_context(patient_id, today, ctx, chat_msg.id, session)
    await session.commit()
    logger.info("[morning] сообщение создано patient=%d", patient_id)


async def deliver_morning_message(patient_id: int, session: AsyncSession) -> None:
    """
    Cron-функция: отправляет утреннее сообщение одному пациенту.
    Вызывается из scheduler в 08:00. Session создаётся снаружи (изолированно).
    """
    today = date.today()
    if await _is_morning_sent_today(patient_id, today, session):
        logger.debug("[morning] пропуск patient=%d — уже отправлено", patient_id)
        return

    ctx = await build_daily_context(patient_id, today, session)
    msg = build_morning_message(ctx)

    chat_msg = ChatMessage(
        patient_id=patient_id,
        role="assistant",
        content=msg["text"],
        tokens_used=0,
        model_used=None,
        domain="routine",
        request_type="morning",
        is_read=False,
        buttons_json=msg["buttons"] if msg["buttons"] else None,
    )
    session.add(chat_msg)
    await session.flush()

    await _upsert_daily_context(patient_id, today, ctx, chat_msg.id, session)
    await session.commit()
    logger.info("[morning] cron: сообщение создано patient=%d", patient_id)


async def get_daily_context_for_llm(patient_id: int, session: AsyncSession) -> str:
    """
    Возвращает короткую строку контекста дня для system prompt GigaChat (~100 токенов).
    Вызывается в chat endpoint при обработке ответного сообщения пациента.
    """
    today = date.today()
    row = await session.execute(
        text("""
            SELECT context_json
            FROM llm.patient_daily_context
            WHERE patient_id = :pid AND context_date = :d
        """),
        {"pid": patient_id, "d": today},
    )
    rec = row.fetchone()
    if rec is None:
        return ""

    ctx = rec[0]
    if isinstance(ctx, str):
        ctx = json.loads(ctx)

    parts: list[str] = []
    if ctx.get("dialysis_today"):
        parts.append("сегодня день диализа")
    if ctx.get("morning_meds_pending", 0) > 0:
        parts.append("утренние лекарства не отмечены")
    if ctx.get("missed_yesterday"):
        parts.append(f"вчера пропущено: {', '.join(ctx['missed_yesterday'])}")
    if ctx.get("streak_medications", 0) >= 3:
        parts.append(f"серия лекарств: {ctx['streak_medications']} дней")

    if not parts:
        return "Пациент сегодня всё выполнил."

    return "Контекст дня: " + "; ".join(parts) + "."
