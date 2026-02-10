# ============================================
# TOBOL Calculator: Расчёт профилей отношения к болезни
# ============================================
# Суммирует баллы по 12 профилям (Г, Р, З, Т, И, Н, М, А, С, Э, П, Д)
# с учётом запрещённых комбинаций, определяет доминирующий тип.

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence

from app.scales.config.tobol import (
    FORBID,
    PROFILE_CODES,
    PROFILE_DESCRIPTIONS,
    TOBOL_COEFFS,
    TOBOL_ITEMS,
)

ScaleResult = Dict[str, Any]


def _validate_question_ids(selected_ids: Sequence[str]) -> None:
    valid_ids = {item.id for item in TOBOL_ITEMS}
    seen: set[str] = set()
    duplicates: set[str] = set()
    for qid in selected_ids:
        if qid in seen:
            duplicates.add(qid)
        else:
            seen.add(qid)
    if duplicates:
        raise ValueError(f"Duplicate answers for questions: {sorted(duplicates)}")

    unknown = [qid for qid in selected_ids if qid not in valid_ids]
    if unknown:
        raise ValueError(f"Unknown question ids: {sorted(unknown)}")


def calculate_tobol_profile(selected_ids: Iterable[str]) -> ScaleResult:
    """Подсчёт профиля ТОБОЛ по списку выбранных утверждений."""

    selected_list = list(selected_ids)
    _validate_question_ids(selected_list)

    raw_scores: Dict[str, int] = {code: 0 for code in PROFILE_CODES}
    forbidden: Dict[str, bool] = {code: False for code in PROFILE_CODES}
    for question_id in selected_list:
        coeffs = TOBOL_COEFFS.get(question_id)
        if coeffs is None:
            raise ValueError(f"Coefficients not found for question {question_id}")

        for profile_code in PROFILE_CODES:
            value = coeffs.get(profile_code)
            if value is None:
                continue
            if value == FORBID:
                forbidden[profile_code] = True
            else:
                raw_scores[profile_code] += int(value)

    total_score = sum(raw_scores.values())

    top_profiles = sorted(
        PROFILE_CODES,
        key=lambda code: raw_scores[code],
        reverse=True,
    )
    top_profiles = [code for code in top_profiles if raw_scores[code] > 0][:3]

    summary_parts = [
        f"{PROFILE_DESCRIPTIONS[code]['label']} ({raw_scores[code]} баллов)"
        for code in top_profiles
    ]
    if not summary_parts:
        summary_parts.append("Значимых профилей не выявлено")

    forbidden_profiles = [
        PROFILE_DESCRIPTIONS[code]["label"] for code, flag in forbidden.items() if flag
    ]
    if forbidden_profiles:
        summary_parts.append(
            "Запрещающие признаки: " + ", ".join(sorted(set(forbidden_profiles)))
        )

    subscales: Dict[str, Dict[str, Any]] = {}
    for code in PROFILE_CODES:
        profile_meta = PROFILE_DESCRIPTIONS.get(code, {})
        subscales[code] = {
            "score": raw_scores[code],
            "forbidden": forbidden[code],
            "label": profile_meta.get("label", code),
            "description": profile_meta.get("description", ""),
        }

    return {
        "total_score": total_score,
        "subscales": subscales,
        "summary": "; ".join(summary_parts),
    }


def calculate_tobol(
    answers: Iterable[Dict[str, Any] | Any],
) -> tuple[ScaleResult, List[Dict[str, Any]]]:
    """Обёртка, преобразующая ответы в список выбранных вопросов."""

    selected_ids: List[str] = []
    raw_log: List[Dict[str, Any]] = []

    for answer in answers:
        question_id = (
            answer.get("question_id")
            if isinstance(answer, dict)
            else getattr(answer, "question_id", None)
        )
        if question_id is None:
            raise ValueError("question_id is required")

        value = (
            answer.get("value") if isinstance(answer, dict) else getattr(answer, "value", None)
        )
        raw_log.append({"question_id": question_id, "value": value})

        if value is None:
            continue
        if value != 0:
            selected_ids.append(str(question_id))

    result = calculate_tobol_profile(selected_ids)
    return result, raw_log

