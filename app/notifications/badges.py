# ============================================
# Notifications: Badges endpoint
# GET /api/notifications/badges
# ============================================
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.users.models import User
from core.db.session import get_async_session

router = APIRouter(prefix="/notifications", tags=["notifications"])


class BadgesResponse(BaseModel):
    vitals: int
    medications: int
    sleep: int
    scales: int
    education: int
    routine: int
    assistant: int


@router.get("/badges", response_model=BadgesResponse)
async def get_badges(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
) -> BadgesResponse:
    """
    Возвращает счётчики незавершённых действий по разделам.
    Используется сайдбаром для отображения бейджей.
    """
    today = date.today()
    today_start = datetime.combine(today, time.min).replace(tzinfo=timezone.utc)
    today_end = today_start + timedelta(days=1)

    # ── Vitals: 1 если нет измерения АД сегодня ─────────────────────────────
    r = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM vitals.bp_measurements
            WHERE user_id = :uid
              AND measured_at >= :start
              AND measured_at < :end
        """),
        {"uid": user.id, "start": today_start, "end": today_end},
    )
    vitals_badge = 0 if (r.scalar_one() or 0) > 0 else 1

    # ── Medications: ожидаемые слоты сегодня − фактические приёмы ──────────
    r = await session.execute(
        text("""
            SELECT COALESCE(SUM(json_array_length(intake_schedule)), 0)
            FROM medications.medication_prescriptions
            WHERE patient_id = :pid
              AND status = 'active'
              AND start_date <= :today
              AND (end_date IS NULL OR end_date >= :today)
        """),
        {"pid": user.id, "today": today},
    )
    total_slots = r.scalar_one() or 0

    r = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM medications.medication_intakes
            WHERE patient_id = :pid
              AND intake_datetime >= :start
              AND intake_datetime < :end
        """),
        {"pid": user.id, "start": today_start, "end": today_end},
    )
    actual_intakes = r.scalar_one() or 0
    medications_badge = max(0, total_slots - actual_intakes)

    # ── Sleep: 1 если нет записи за последние сутки ─────────────────────────
    r = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM sleep.sleep_records
            WHERE patient_id = :pid
              AND sleep_date >= :since
        """),
        {"pid": user.id, "since": today - timedelta(days=1)},
    )
    sleep_badge = 0 if (r.scalar_one() or 0) > 0 else 1

    # ── Scales: активированные точки KDQOL без completed_at ─────────────────
    r = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM kdqol.measurement_points
            WHERE patient_id = :pid
              AND completed_at IS NULL
        """),
        {"pid": user.id},
    )
    scales_badge = r.scalar_one() or 0

    # ── Education: активные уроки без отметки завершения ────────────────────
    r = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM education.lessons l
            WHERE l.is_active = TRUE
              AND NOT EXISTS (
                  SELECT 1 FROM education.lesson_progress lp
                  WHERE lp.lesson_id = l.id
                    AND lp.user_id = :uid
                    AND lp.is_completed = TRUE
              )
        """),
        {"uid": user.id},
    )
    education_badge = r.scalar_one() or 0

    # ── Routine: есть активный baseline, но нет верификации за сегодня ──────
    # (пользователь использует модуль, но день ещё не подведён)
    r = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM routine.baseline_routines br
            WHERE br.patient_id = :pid
              AND br.valid_to IS NULL
              AND NOT EXISTS (
                  SELECT 1 FROM routine.daily_verifications dv
                  WHERE dv.patient_id = :pid
                    AND dv.verification_date = :today
              )
        """),
        {"pid": user.id, "today": today},
    )
    routine_badge = min(1, r.scalar_one() or 0)

    # ── Assistant: непрочитанные сообщения ассистента ───────────────────────
    r = await session.execute(
        text("""
            SELECT COUNT(*)
            FROM llm.chat_messages
            WHERE patient_id = :pid
              AND role = 'assistant'
              AND is_read = FALSE
        """),
        {"pid": user.id},
    )
    assistant_badge = r.scalar_one() or 0

    return BadgesResponse(
        vitals=vitals_badge,
        medications=medications_badge,
        sleep=sleep_badge,
        scales=scales_badge,
        education=education_badge,
        routine=routine_badge,
        assistant=assistant_badge,
    )
