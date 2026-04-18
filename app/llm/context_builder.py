"""
Context Builder — сбор данных пациента из БД для передачи в LLM.

Функции:
  build_context(patient_id, db) -> dict
    Собирает все разделы. Если раздел упал — логирует warning, возвращает [].

  format_context_for_llm(context) -> str
    Превращает dict в читаемый текст для системного промпта.
    Пустые разделы пропускаются.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("gpt-support-llm.context_builder")


def _extract_first_int(text: str) -> int | None:
    match = re.search(r"(\d+)", text)
    if not match:
        return None
    return int(match.group(1))


def _build_patient_summary_items(context: dict) -> list[dict[str, object]]:
    """Собирает summary items с тегами и приоритетами для дальнейшего отбора."""
    items: list[dict[str, object]] = []

    sleep_summary = context.get("sleep_summary", [])
    if sleep_summary:
        sleep_line = str(sleep_summary[0]).lower()
        if "снижается" in sleep_line:
            items.append({"text": "В последние дни сон ухудшился.", "tags": ["sleep"], "priority": 100})
        elif "среднее" in sleep_line:
            hours_match = re.search(r"среднее\s+([\d.,]+)", sleep_line)
            if hours_match:
                try:
                    avg_hours = float(hours_match.group(1).replace(",", "."))
                except ValueError:
                    avg_hours = None
                if avg_hours is not None and avg_hours < 6:
                    items.append({"text": "В последние дни сна было меньше обычного.", "tags": ["sleep"], "priority": 95})
                else:
                    items.append({"text": "Сон в последние дни был относительно стабильным.", "tags": ["sleep"], "priority": 40})

    med_adherence = context.get("medication_adherence", [])
    if med_adherence:
        pct = _extract_first_int(str(med_adherence[0]))
        if pct is not None:
            if pct < 70:
                items.append({"text": "Приём лекарств в последнее время был неполным.", "tags": ["medication", "routine"], "priority": 100})
            elif pct < 90:
                items.append({"text": "Приём лекарств в последние дни был не совсем регулярным.", "tags": ["medication", "routine"], "priority": 80})

    routine_summary = context.get("routine_summary", [])
    if routine_summary:
        control_pct = _extract_first_int(str(routine_summary[0]).split("контроль")[-1])
        if control_pct is not None and control_pct < 70:
            items.append({"text": "Повседневная рутина в последние дни давалась тяжело.", "tags": ["routine"], "priority": 90})

    recent_water = context.get("recent_water", [])
    if recent_water:
        water_ml = _extract_first_int(str(recent_water[0]))
        if water_ml is not None:
            items.append({"text": "Контроль жидкости остаётся важной частью повседневной рутины.", "tags": ["water", "routine"], "priority": 50})

    recent_vitals = context.get("recent_vitals", [])
    elevated_bp = False
    for line in recent_vitals[:3]:
        match = re.search(r"АД\s+(\d+)/(\d+)", str(line))
        if match:
            systolic = int(match.group(1))
            diastolic = int(match.group(2))
            if systolic >= 140 or diastolic >= 90:
                elevated_bp = True
                break
    if elevated_bp:
        items.append({"text": "Давление несколько раз было выше обычного.", "tags": ["clinical"], "priority": 90})

    scale_scores = " ".join(str(item).lower() for item in context.get("last_scale_scores", []))
    if any(token in scale_scores for token in ("hads", "gad", "phq", "pss")):
        items.append({"text": "По последним шкалам есть признаки эмоционального напряжения.", "tags": ["emotion"], "priority": 85})

    rag_context = context.get("rag_context", [])
    if rag_context:
        items.append({"text": "По этой теме можно предложить пациенту подходящий обучающий материал.", "tags": ["cta_lesson"], "priority": 30})

    return items


def _build_patient_summary(context: dict) -> list[str]:
    """Обратная совместимость: полный список summary-текстов."""
    return [str(item["text"]) for item in _build_patient_summary_items(context)]


def _clip_rag_fragment(text: str, *, limit: int = 240) -> str:
    compact = " ".join(str(text).split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _strip_lesson_framing(chunk: str) -> str:
    kept_lines: list[str] = []
    for line in str(chunk or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if any(
            stripped.startswith(prefix)
            for prefix in ("Урок:", "Тема:", "Тип карточки:", "Раздел:")
        ):
            continue
        kept_lines.append(stripped)
    return " ".join(kept_lines)


def _looks_like_routine_fragment(text: str) -> bool:
    lower = str(text or "").lower()
    return any(
        marker in lower
        for marker in (
            "попроб",
            "сделай",
            "сниз",
            "коротк",
            "пауз",
            "выбери",
            "запиши",
            "убери",
            "повтори",
            "ритуал",
            "замедл",
            "вдох",
            "выдох",
        )
    )


def _build_role_specific_rag_views(
    rag_context: list[str],
    rag_grounding_items: list[dict[str, object]],
    standalone_psych_support_items: list[str] | None = None,
) -> dict[str, list[str]]:
    routine_items: list[str] = []
    seen_routine: set[str] = set()
    for item in rag_grounding_items or []:
        cleaned = _strip_lesson_framing(str(item.get("chunk") or ""))
        if not cleaned or not _looks_like_routine_fragment(cleaned):
            continue
        if cleaned in seen_routine:
            continue
        seen_routine.add(cleaned)
        routine_items.append(cleaned)

    psych_support_items: list[str] = []
    seen_psych_support: set[str] = set()
    for item in rag_grounding_items or []:
        practice = item.get("practice") or {}
        if not isinstance(practice, dict) or not practice:
            continue
        title = str(practice.get("title") or "").strip()
        lesson_title = str(item.get("lesson_title") or "").strip()
        if not title:
            continue
        rendered = f"Практика по теме: {title}"
        if lesson_title:
            rendered += f". Связанный материал: {lesson_title}"
        lowered = rendered.lower()
        if lowered in seen_psych_support:
            continue
        seen_psych_support.add(lowered)
        psych_support_items.append(rendered)

    for item in standalone_psych_support_items or []:
        rendered = str(item or "").strip()
        if not rendered:
            continue
        lowered = rendered.lower()
        if lowered in seen_psych_support:
            continue
        seen_psych_support.add(lowered)
        psych_support_items.append(rendered)

    return {
        "psych_support": psych_support_items,
        "routine": routine_items,
        "education": list(rag_context or []),
    }


def _extract_module_ids_from_grounding_items(
    rag_grounding_items: list[dict[str, object]],
) -> list[str]:
    module_ids: list[str] = []
    seen: set[str] = set()
    for item in rag_grounding_items or []:
        lesson_code = str(item.get("lesson_code") or "")
        match = re.match(r"^(\d{2})_", lesson_code)
        if not match:
            continue
        module_id = match.group(1)
        if module_id in seen:
            continue
        seen.add(module_id)
        module_ids.append(module_id)
    return module_ids


def _render_standalone_psych_support_practice(practice: object) -> str:
    title = str(getattr(practice, "title", "") or "").strip()
    if not title:
        return ""

    parts = [f"Практика: {title}"]

    tagline = str(getattr(practice, "tagline", "") or "").strip()
    if tagline:
        parts.append(f"Зачем: {tagline}")

    context = str(getattr(practice, "context", "") or "").strip()
    if context:
        parts.append(f"Контекст: {context}")

    instruction = getattr(practice, "instruction", None) or []
    if isinstance(instruction, list):
        short_steps = [str(step).strip() for step in instruction[:2] if str(step).strip()]
        if short_steps:
            parts.append(f"Короткие шаги: {' '.join(short_steps)}")

    return ". ".join(parts)


async def _get_standalone_psych_support_items(
    rag_grounding_items: list[dict[str, object]],
    db: AsyncSession,
) -> list[str]:
    from app.practices.models import StandalonePractice

    module_ids = _extract_module_ids_from_grounding_items(rag_grounding_items)
    if not module_ids:
        return []

    result = await db.execute(
        select(StandalonePractice)
        .where(
            StandalonePractice.is_active.is_(True),
            StandalonePractice.module_id.in_(module_ids),
        )
        .order_by(StandalonePractice.module_id.asc(), StandalonePractice.id.asc())
    )

    items: list[str] = []
    seen_modules: set[str] = set()
    for practice in result.scalars().all():
        module_id = str(getattr(practice, "module_id", "") or "")
        if not module_id or module_id in seen_modules:
            continue
        rendered = _render_standalone_psych_support_practice(practice)
        if not rendered:
            continue
        seen_modules.add(module_id)
        items.append(rendered)
    return items


def _make_cta_metadata(
    *,
    lesson_id: int,
    lesson_code: str,
    lesson_title: str,
    is_read: bool,
    is_completed: bool,
    has_passed_test: bool,
    practice: dict[str, object] | None,
) -> dict[str, object]:
    if not is_read:
        return {
            "cta_type": "lesson",
            "cta_reason": "lesson_unread",
            "cta_label": lesson_title,
            "cta_target": {"lesson_id": lesson_id, "lesson_code": lesson_code},
        }
    if has_passed_test and practice:
        return {
            "cta_type": "practice",
            "cta_reason": "lesson_mastered",
            "cta_label": str(practice["title"]),
            "cta_target": {
                "practice_id": practice["id"],
                "lesson_id": lesson_id,
                "lesson_code": lesson_code,
            },
        }
    if is_read:
        return {
            "cta_type": "lesson",
            "cta_reason": "lesson_needs_review",
            "cta_label": lesson_title,
            "cta_target": {"lesson_id": lesson_id, "lesson_code": lesson_code},
        }
    return {
        "cta_type": "none",
        "cta_reason": "no_cta",
        "cta_label": None,
        "cta_target": None,
    }


async def _build_rag_grounding_items(
    patient_id: int,
    modules: list[dict[str, object]],
    db: AsyncSession,
) -> list[dict[str, object]]:
    if not modules:
        return []

    from app.education.models import LessonProgress, LessonTest, LessonTestResult, Practice

    valid_modules: list[dict[str, object]] = []
    for module in modules:
        try:
            int(module["lesson_id"])
        except (KeyError, TypeError, ValueError):
            continue
        valid_modules.append(module)

    if not valid_modules:
        return []

    lesson_ids = sorted({int(module["lesson_id"]) for module in valid_modules})

    progress_result = await db.execute(
        select(LessonProgress).where(
            LessonProgress.user_id == patient_id,
            LessonProgress.lesson_id.in_(lesson_ids),
        )
    )
    progress_rows = progress_result.scalars().all()
    progress_by_lesson_id = {int(row.lesson_id): row for row in progress_rows}

    tests_result = await db.execute(
        select(LessonTest.id, LessonTest.lesson_id).where(
            LessonTest.lesson_id.in_(lesson_ids),
            LessonTest.is_active.is_(True),
        )
    )
    test_rows = tests_result.all()
    test_id_to_lesson_id = {int(test_id): int(lesson_id) for test_id, lesson_id in test_rows}
    test_ids = list(test_id_to_lesson_id.keys())

    passed_by_lesson_id = {lesson_id: False for lesson_id in lesson_ids}
    best_score_by_lesson_id = {lesson_id: None for lesson_id in lesson_ids}
    if test_ids:
        test_results = await db.execute(
            select(
                LessonTestResult.test_id,
                LessonTestResult.score,
                LessonTestResult.max_score,
                LessonTestResult.passed,
            ).where(
                LessonTestResult.user_id == patient_id,
                LessonTestResult.test_id.in_(test_ids),
            )
        )
        for test_id, score, max_score, passed in test_results.all():
            lesson_id = test_id_to_lesson_id.get(int(test_id))
            if lesson_id is None:
                continue
            passed_by_lesson_id[lesson_id] = passed_by_lesson_id[lesson_id] or bool(passed)
            if score is not None and max_score:
                ratio = float(score / max_score) if isinstance(score, (Decimal, float, int)) else None
                current = best_score_by_lesson_id.get(lesson_id)
                if ratio is not None and (current is None or ratio > current):
                    best_score_by_lesson_id[lesson_id] = ratio

    practices_result = await db.execute(
        select(Practice).where(
            Practice.lesson_id.in_(lesson_ids),
            Practice.is_active.is_(True),
        ).order_by(Practice.lesson_id.asc(), Practice.order_index.asc(), Practice.id.asc())
    )
    practice_by_lesson_id: dict[int, dict[str, object]] = {}
    for practice in practices_result.scalars().all():
        lesson_id = int(practice.lesson_id)
        if lesson_id in practice_by_lesson_id:
            continue
        practice_by_lesson_id[lesson_id] = {
            "id": int(practice.id),
            "title": practice.title,
        }

    grounding_items: list[dict[str, object]] = []
    for index, module in enumerate(valid_modules):
        lesson_id = int(module["lesson_id"])
        progress = progress_by_lesson_id.get(lesson_id)
        practice = practice_by_lesson_id.get(lesson_id)
        is_read = progress is not None and int(progress.last_card_index or 0) > 0
        is_completed = bool(progress.is_completed) if progress is not None else False
        has_passed_test = bool(passed_by_lesson_id.get(lesson_id, False))
        item = {
            "rag_index": index,
            "lesson_id": lesson_id,
            "lesson_code": str(module.get("code") or ""),
            "lesson_title": str(module.get("title") or ""),
            "lesson_topic": str(module.get("topic") or ""),
            "card_index": int(module.get("card_index") or 0),
            "chunk": str(module.get("chunk") or ""),
            "is_read": is_read,
            "is_completed": is_completed,
            "has_passed_test": has_passed_test,
            "best_test_score_ratio": best_score_by_lesson_id.get(lesson_id),
            "practice": practice,
        }
        item["cta"] = _make_cta_metadata(
            lesson_id=lesson_id,
            lesson_code=item["lesson_code"],
            lesson_title=item["lesson_title"],
            is_read=is_read,
            is_completed=is_completed,
            has_passed_test=has_passed_test,
            practice=practice,
        )
        grounding_items.append(item)
    return grounding_items


def select_patient_summary_for_prompt(
    context: dict,
    *,
    policy_name: str,
    parser_domain_hints: list[str] | None = None,
    effective_domain: str | None = None,
) -> list[str]:
    """Отбирает релевантные summary-пункты для prompt под текущий policy."""
    items = list(context.get("patient_summary_items", []))
    if not items:
        return list(context.get("patient_summary", []))[:3]

    parser_domain_hints = parser_domain_hints or []
    policy_tag_order: dict[str, list[str]] = {
        "sleep_support": ["sleep", "emotion", "cta_lesson", "cta_practice", "medication"],
        "emotional_support_now": ["emotion", "sleep", "cta_practice", "cta_lesson"],
        "routine_support": ["medication", "routine", "water", "emotion", "cta_lesson", "cta_practice"],
        "default_support": [],
        "clinical_caution": ["clinical", "emotion", "sleep", "medication"],
    }
    allowed_tags = policy_tag_order.get(policy_name, [])
    if not allowed_tags:
        if effective_domain == "sleep" or "sleep" in parser_domain_hints:
            allowed_tags = ["sleep", "emotion", "cta_lesson"]
        elif effective_domain == "routine" or "routine" in parser_domain_hints:
            allowed_tags = ["medication", "routine", "water", "emotion"]
        elif effective_domain == "emotion" or "emotion" in parser_domain_hints:
            allowed_tags = ["emotion", "sleep", "cta_practice"]
        else:
            allowed_tags = ["emotion", "sleep", "medication", "routine", "cta_lesson"]

    tag_rank = {tag: index for index, tag in enumerate(allowed_tags)}
    selected: list[dict[str, object]] = []
    for item in items:
        tags = list(item.get("tags", []))
        matching_tags = [tag for tag in tags if tag in tag_rank]
        if not matching_tags:
            continue
        primary_rank = min(tag_rank[tag] for tag in matching_tags)
        selected.append(
            {
                "text": item["text"],
                "priority": int(item.get("priority", 0)),
                "rank": primary_rank,
            }
        )

    selected.sort(key=lambda item: (item["rank"], -int(item["priority"])))
    prompt_summary = [str(item["text"]) for item in selected[:3]]
    if prompt_summary:
        return prompt_summary

    return [str(item["text"]) for item in items[:2]]
# ---------------------------------------------------------------------------
# Отдельные разделы
# ---------------------------------------------------------------------------


async def _get_recent_vitals(patient_id: int, db: AsyncSession) -> list[str]:
    """Последние 7 записей АД из vitals.bp_measurements."""
    from app.vitals.models import BPMeasurement

    since = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(BPMeasurement)
        .where(
            BPMeasurement.user_id == patient_id,
            BPMeasurement.measured_at >= since,
        )
        .order_by(BPMeasurement.measured_at.desc())
        .limit(7)
    )
    records = result.scalars().all()

    lines = []
    for r in records:
        date_str = r.measured_at.strftime("%d.%m")
        lines.append(f"АД {r.systolic}/{r.diastolic} ({date_str})")
    return lines


async def _get_medication_adherence(patient_id: int, db: AsyncSession) -> list[str]:
    """% приёма лекарств за 7 дней из medication_intakes vs prescriptions."""
    from app.medications.models import MedicationIntake, MedicationPrescription

    since = datetime.utcnow() - timedelta(days=7)

    # Записанные приёмы за 7 дней
    result = await db.execute(
        select(func.count(MedicationIntake.id)).where(
            MedicationIntake.patient_id == patient_id,
            MedicationIntake.intake_datetime >= since,
        )
    )
    taken = result.scalar() or 0

    # Ожидаемые приёмы: активные назначения × 7 дней
    result = await db.execute(
        select(func.sum(MedicationPrescription.frequency_times_per_day)).where(
            MedicationPrescription.patient_id == patient_id,
            MedicationPrescription.status == "active",
        )
    )
    freq_sum = result.scalar() or 0
    expected = int(freq_sum) * 7

    if expected == 0:
        return []

    pct = min(100, round(taken / expected * 100))
    return [f"Приём лекарств: {pct}% за 7 дней ({taken} из {expected})"]


async def _get_sleep_summary(patient_id: int, db: AsyncSession) -> list[str]:
    """Среднее сна и тренд из sleep.sleep_records."""
    from app.sleep_tracker.models import SleepRecord

    since = (datetime.utcnow() - timedelta(days=7)).date()
    result = await db.execute(
        select(SleepRecord)
        .where(
            SleepRecord.patient_id == patient_id,
            SleepRecord.sleep_date >= since,
        )
        .order_by(SleepRecord.sleep_date.asc())
        .limit(7)
    )
    records = result.scalars().all()

    if not records:
        return []

    hours_list = [r.tst_minutes / 60 for r in records if r.tst_minutes]
    if not hours_list:
        return []

    avg_hours = round(sum(hours_list) / len(hours_list), 1)

    # Тренд: сравниваем первую и вторую половину
    mid = len(hours_list) // 2
    if mid > 0 and len(hours_list) > 2:
        first_half = sum(hours_list[:mid]) / mid
        second_half = sum(hours_list[mid:]) / (len(hours_list) - mid)
        diff = second_half - first_half
        if diff > 0.5:
            trend = "растёт"
        elif diff < -0.5:
            trend = "снижается"
        else:
            trend = "стабильно"
    else:
        trend = "стабильно"

    return [f"Сон: среднее {avg_hours}ч, тренд {trend}"]


async def _get_active_practices(patient_id: int, db: AsyncSession) -> list[str]:
    """
    TODO: таблица practice_assignments не реализована.
    В текущей схеме назначения практик пациенту не хранятся отдельно.
    Возвращаем пустой список.
    """
    return []


async def _get_recent_weight(patient_id: int, db: AsyncSession) -> list[str]:
    """Последние 3 записи веса за 14 дней из vitals.weight_measurements."""
    from app.vitals.models import WeightMeasurement

    since = datetime.utcnow() - timedelta(days=14)
    result = await db.execute(
        select(WeightMeasurement)
        .where(
            WeightMeasurement.user_id == patient_id,
            WeightMeasurement.measured_at >= since,
        )
        .order_by(WeightMeasurement.measured_at.desc())
        .limit(3)
    )
    records = result.scalars().all()

    return [
        f"Вес: {float(r.weight)} кг ({r.measured_at.strftime('%d.%m')})"
        for r in records
    ]


async def _get_recent_water(patient_id: int, db: AsyncSession) -> list[str]:
    """Среднее потребление воды за 7 дней из vitals.water_intake."""
    from app.vitals.models import WaterIntake

    since = datetime.utcnow() - timedelta(days=7)
    result = await db.execute(
        select(func.avg(WaterIntake.volume_ml)).where(
            WaterIntake.user_id == patient_id,
            WaterIntake.measured_at >= since,
        )
    )
    avg_ml = result.scalar()

    if avg_ml is None:
        return []

    return [f"Вода: среднее {round(avg_ml)} мл/день за 7 дней"]


async def _get_routine_summary(patient_id: int, db: AsyncSession) -> list[str]:
    """Верификации рутины за 7 дней из routine.daily_verifications."""
    from datetime import date as date_type

    from app.routine.models import DailyVerification

    since = (datetime.utcnow() - timedelta(days=7)).date()
    result = await db.execute(
        select(DailyVerification).where(
            DailyVerification.patient_id == patient_id,
            DailyVerification.verification_date >= since,
        )
    )
    records = result.scalars().all()

    if not records:
        return []

    days_count = len(records)
    avg_score = round(sum(r.day_control_score for r in records) / days_count)
    return [f"Рутина: {days_count} из 7 дней, средний контроль {avg_score}%"]


async def _get_rag_context(
    patient_id: int, query: str, db: AsyncSession
) -> list[str]:
    """
    RAG: найти образовательные модули, релевантные запросу пациента.

    Для прочитанных уроков — добавляет релевантный фрагмент.
    Для непрочитанных — предлагает ознакомиться.
    """
    from app.rag.retriever import retrieve_relevant_modules

    modules = await retrieve_relevant_modules(query, patient_id, db, top_k=2)
    lines = []
    for m in modules:
        if m["is_read"]:
            lines.append(
                f"Пациент читал урок «{m['title']}». "
                f"Релевантный фрагмент: {m['chunk'][:200]}"
            )
        else:
            lines.append(
                f"По теме «{m['title']}» есть урок — можешь предложить пациенту."
            )
    return lines


async def _get_practices_summary(patient_id: int, db: AsyncSession) -> list[str]:
    """Выполненные практики за 7 дней + доступные активные практики (limit 5)."""
    from app.practices.models import PracticeCompletion, StandalonePractice

    since = datetime.utcnow() - timedelta(days=7)

    result = await db.execute(
        select(func.count(PracticeCompletion.id)).where(
            PracticeCompletion.patient_id == patient_id,
            PracticeCompletion.completed_at >= since,
        )
    )
    completed_count = result.scalar() or 0

    result = await db.execute(
        select(StandalonePractice)
        .where(StandalonePractice.is_active == True)  # noqa: E712
        .limit(5)
    )
    practices = result.scalars().all()

    if completed_count == 0 and not practices:
        return []

    lines = []
    if completed_count > 0:
        lines.append(f"Практики выполнено за 7 дней: {completed_count}")
    if practices:
        items = ", ".join(
            f"{p.title} ({p.icf_domain})" if p.icf_domain else p.title
            for p in practices
        )
        lines.append(f"Доступные практики: {items}")
    return lines


async def _get_last_scale_scores(patient_id: int, db: AsyncSession) -> list[str]:
    """Последние результаты каждой шкалы из scales.scale_results."""
    from app.scales.models import ScaleResult

    result = await db.execute(
        select(ScaleResult)
        .where(ScaleResult.user_id == patient_id)
        .order_by(ScaleResult.measured_at.desc())
        .limit(50)
    )
    records = result.scalars().all()

    # Берём последний результат по каждой шкале (дедупликация)
    seen: dict[str, ScaleResult] = {}
    for r in records:
        if r.scale_code not in seen:
            seen[r.scale_code] = r

    lines = []
    for scale_code, r in seen.items():
        date_str = r.measured_at.strftime("%d.%m")
        score = None
        if isinstance(r.result_json, dict):
            score = r.result_json.get("total_score") or r.result_json.get("score")
        if score is not None:
            lines.append(f"{scale_code}: {score} ({date_str})")
        else:
            lines.append(f"{scale_code}: ({date_str})")
    return lines


async def _get_chat_history(patient_id: int, db: AsyncSession) -> list[dict]:
    """Последние 5 сообщений из llm.chat_messages."""
    from app.models.llm import ChatMessage

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.patient_id == patient_id)
        .order_by(ChatMessage.created_at.desc())
        .limit(5)
    )
    messages = list(reversed(result.scalars().all()))
    return [{"role": m.role, "content": m.content} for m in messages]


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------


async def build_context(
    patient_id: int, db: AsyncSession, query: str = ""
) -> dict:
    """
    Собирает данные пациента из БД.
    Если раздел вызвал исключение — логирует warning и возвращает пустой список.

    Args:
        patient_id: ID пациента
        db:         AsyncSession
        query:      текст запроса пользователя (для RAG; пропускается если пустой
                    или короче 15 символов)

    Returns:
        dict с ключами: recent_vitals, medication_adherence, sleep_summary,
        active_practices, last_scale_scores, chat_history, rag_context
    """
    sections: dict[str, any] = {
        "recent_vitals": _get_recent_vitals,
        "medication_adherence": _get_medication_adherence,
        "sleep_summary": _get_sleep_summary,
        "active_practices": _get_active_practices,
        "last_scale_scores": _get_last_scale_scores,
        "recent_weight": _get_recent_weight,
        "recent_water": _get_recent_water,
        "routine_summary": _get_routine_summary,
        "practices_summary": _get_practices_summary,
        "chat_history": _get_chat_history,
    }

    context: dict = {}
    for name, fn in sections.items():
        try:
            context[name] = await fn(patient_id, db)
        except Exception as exc:
            logger.warning("[context_builder] Раздел '%s' упал: %s", name, exc)
            context[name] = []

    # RAG: ищем релевантные образовательные модули только для содержательных запросов
    context["rag_context"] = []
    if len(query) > 15:
        try:
            context["rag_context"] = await _get_rag_context(patient_id, query, db)
        except Exception as exc:
            logger.warning("[context_builder] RAG retriever упал: %s", exc)

    return context


def format_context_for_llm(context: dict) -> str:
    """
    Превращает dict контекста в читаемый текст для системного промпта.
    Пустые разделы пропускаются.

    Returns:
        Строка вида "=== Данные пациента ===\\n..." или "" если нет данных.
    """
    labels = {
        "recent_vitals": "Витальные показатели",
        "medication_adherence": "Приём лекарств",
        "sleep_summary": "Сон",
        "active_practices": "Активные практики",
        "last_scale_scores": "Шкалы",
        "recent_weight": "Вес",
        "recent_water": "Потребление воды",
        "routine_summary": "Рутина",
        "practices_summary": "Практики",
        "rag_context": "Образовательные модули",
        # chat_history передаётся отдельно в messages — здесь не выводим
    }

    lines: list[str] = []
    for key, label in labels.items():
        values = context.get(key, [])
        if not values:
            continue
        # rag_context содержит полные предложения — выводим по одному на строку
        if key == "rag_context":
            lines.append(f"{label}:")
            for item in values:
                lines.append(f"  - {item}")
        else:
            value_str = ", ".join(str(v) for v in values)
            lines.append(f"{label}: {value_str}")

    if not lines:
        return ""

    return "=== Данные пациента ===\n" + "\n".join(lines)
