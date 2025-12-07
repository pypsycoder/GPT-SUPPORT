from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.scales.config.hads import HADS_CONFIG
from app.scales.models import ScaleResult


def get_scale_config(scale_code: str) -> dict:
    """Возвращаем конфиг шкалы по её коду."""

    if scale_code.upper() == "HADS":
        return HADS_CONFIG
    raise ValueError(f"Unknown scale code: {scale_code}")


def calculate_hads_result(
    scale_config: dict, answers: List[Dict[str, str]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Считаем баллы по субшкалам и логируем ответы."""

    # индексируем вопросы
    questions_map = {question["id"]: question for question in scale_config.get("questions", [])}
    expected_ids = set(questions_map.keys())

    # накапливаем баллы по субшкалам
    subscale_scores = {"ANX": 0, "DEP": 0}
    answers_log: List[Dict[str, Any]] = []
    seen_questions: set[str] = set()

    for answer in answers:
        # поддерживаем как словари, так и Pydantic-модели
        question_id = (
            answer.get("question_id") if isinstance(answer, dict) else getattr(answer, "question_id", None)
        )
        option_id = (
            answer.get("option_id") if isinstance(answer, dict) else getattr(answer, "option_id", None)
        )

        if question_id in seen_questions:
            raise ValueError(f"Duplicate answer for question {question_id}")
        seen_questions.add(question_id)

        question = questions_map.get(question_id)
        if not question:
            raise ValueError(f"Unknown question id: {question_id}")

        option = next((opt for opt in question.get("options", []) if opt["id"] == option_id), None)
        if not option:
            raise ValueError(f"Unknown option id: {option_id} for question {question_id}")

        score_value = int(option["score"])
        subscale = question["subscale"]
        if subscale not in subscale_scores:
            subscale_scores[subscale] = 0
        subscale_scores[subscale] += score_value

        # логируем исходные ответы
        answers_log.append(
            {
                "question_id": question_id,
                "option_id": option_id,
                "score_value": score_value,
            }
        )

    answered_ids = seen_questions
    if answered_ids != expected_ids:
        missing = expected_ids - answered_ids
        extra = answered_ids - expected_ids
        details = []
        if missing:
            details.append(f"missing: {sorted(missing)}")
        if extra:
            details.append(f"extra: {sorted(extra)}")
        message = "Not all questions are answered"
        if details:
            message = f"{message} ({'; '.join(details)})"
        raise ValueError(message)

    # применяем cutoffs и формируем результат
    result_json: Dict[str, Any] = {}
    cutoffs = scale_config.get("cutoffs", {})
    for subscale, score in subscale_scores.items():
        ranges = cutoffs.get(subscale, [])
        matched = next((rng for rng in ranges if rng["min"] <= score <= rng["max"]), None)
        if not matched:
            raise ValueError(f"No cutoff matched for subscale {subscale} and score {score}")

        result_json[subscale] = {
            "score": score,
            "level": matched["level"],
            "label": matched["label"],
        }

    return result_json, answers_log


async def save_scale_result(
    session: AsyncSession,
    user_id: int,
    scale_code: str,
    scale_version: str,
    result_json: Dict[str, Any],
    answers_log: List[Dict[str, Any]],
) -> ScaleResult:
    """Сохраняем результат прохождения шкалы в БД."""

    scale_result = ScaleResult(
        user_id=user_id,
        scale_code=scale_code,
        scale_version=scale_version,
        measured_at=datetime.utcnow(),
        result_json=result_json,
        answers_json=answers_log,
    )

    # сохраняем результат в базе
    session.add(scale_result)
    await session.flush()
    await session.commit()
    await session.refresh(scale_result)
    return scale_result
