# ============================================
# PSS-10 Calculator: Расчёт воспринимаемого стресса
# ============================================
# КРИТИЧНО: вопросы 4, 5, 7, 8 — реверсные.
# Формула реверсии: score = 4 - raw_value.
# Без этого итоговый балл будет неверным.
#
# Результат: total_score (0–40) + две субшкалы:
#   perceived_stress  — прямые вопросы 1,2,3,6,9,10 (0–24)
#   perceived_coping  — реверсные вопросы 4,5,7,8 (0–16)

from __future__ import annotations

from typing import Any, Dict, List, Union

from app.scales.config.pss10 import PSS10_CONFIG


def calculate_pss10(answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Считаем результат по шкале ШВС-10 (PSS-10).

    Принимает список ответов {question_id, option_id}.
    Возвращает (result_json, answers_log).

    ВАЖНО: вопросы pss_q4, pss_q5, pss_q7, pss_q8 реверсируются
    по формуле score = 4 - raw_value до суммирования.
    """

    questions_map = {q["id"]: q for q in PSS10_CONFIG["questions"]}
    expected_ids = set(questions_map.keys())

    subscale_scores: Dict[str, int] = {"perceived_stress": 0, "perceived_coping": 0}
    answers_log: List[Dict[str, Any]] = []
    seen_questions: set[str] = set()

    for answer in answers:
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

        option = next((opt for opt in question["options"] if opt["id"] == option_id), None)
        if not option:
            raise ValueError(f"Unknown option id: {option_id} for question {question_id}")

        raw_value = int(option["value"])

        # РЕВЕРСИЯ: вопросы 4, 5, 7, 8
        if question["reverse"]:
            score_value = 4 - raw_value
        else:
            score_value = raw_value

        subscale = question["subscale"]
        subscale_scores[subscale] += score_value

        answers_log.append(
            {
                "question_id": question_id,
                "option_id": option_id,
                "raw_value": raw_value,
                "score_value": score_value,
                "reversed": question["reverse"],
            }
        )

    # Проверяем, что ответили на все вопросы
    if seen_questions != expected_ids:
        missing = expected_ids - seen_questions
        extra = seen_questions - expected_ids
        details = []
        if missing:
            details.append(f"missing: {sorted(missing)}")
        if extra:
            details.append(f"extra: {sorted(extra)}")
        message = "Not all questions are answered"
        if details:
            message = f"{message} ({'; '.join(details)})"
        raise ValueError(message)

    total_score = subscale_scores["perceived_stress"] + subscale_scores["perceived_coping"]

    # Определяем уровень по порогам
    thresholds = PSS10_CONFIG["thresholds"]
    threshold = next(
        (t for t in thresholds if t["min"] <= total_score <= t["max"]),
        None,
    )
    if not threshold:
        raise ValueError(f"No threshold matched for total_score={total_score}")

    level = threshold["level"]
    label = threshold["label"]
    patient_advice = PSS10_CONFIG["patient_result_texts"][level]
    subscale_meta = PSS10_CONFIG["subscales"]

    result_json: Dict[str, Any] = {
        "total_score": total_score,
        "level": level,
        "label": label,
        "summary": f"Общий балл: {total_score} — {label}",
        "subscales": {
            "perceived_stress": {
                "score": subscale_scores["perceived_stress"],
                "description": subscale_meta["perceived_stress"]["description"],
            },
            "perceived_coping": {
                "score": subscale_scores["perceived_coping"],
                "description": subscale_meta["perceived_coping"]["description"],
            },
        },
        "patient_advice": patient_advice,
    }

    return result_json, answers_log
