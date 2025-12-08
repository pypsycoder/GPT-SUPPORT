from __future__ import annotations

from typing import Any, Dict, List, Union

from app.scales.config.hads import HADS_CONFIG


def calculate_hads(answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Считаем результат по шкале HADS."""

    questions_map = {question["id"]: question for question in HADS_CONFIG.get("questions", [])}
    expected_ids = set(questions_map.keys())

    subscale_scores = {"ANX": 0, "DEP": 0}
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

        option = next((opt for opt in question.get("options", []) if opt["id"] == option_id), None)
        if not option:
            raise ValueError(f"Unknown option id: {option_id} for question {question_id}")

        score_value = int(option["score"])
        subscale = question["subscale"]
        if subscale not in subscale_scores:
            subscale_scores[subscale] = 0
        subscale_scores[subscale] += score_value

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

    subscales: Dict[str, Dict[str, Any]] = {}
    cutoffs = HADS_CONFIG.get("cutoffs", {})
    for subscale, score in subscale_scores.items():
        ranges = cutoffs.get(subscale, [])
        matched = next((rng for rng in ranges if rng["min"] <= score <= rng["max"]), None)
        if not matched:
            raise ValueError(f"No cutoff matched for subscale {subscale} and score {score}")

        subscales[subscale] = {
            "score": score,
            "level": matched["level"],
            "label": matched["label"],
        }

    anxiety = subscales.get("ANX", {})
    depression = subscales.get("DEP", {})
    total_score = subscale_scores.get("ANX", 0) + subscale_scores.get("DEP", 0)

    severity_rank = {"normal": 0, "borderline": 1, "clinical": 2}
    anxiety_level = anxiety.get("level")
    depression_level = depression.get("level")
    total_level = max(
        severity_rank.get(anxiety_level, 0),
        severity_rank.get(depression_level, 0),
    )
    level_by_rank = {v: k for k, v in severity_rank.items()}
    total_level_code = level_by_rank.get(total_level, "normal")

    worst_label = (
        anxiety.get("label")
        if total_level_code == anxiety_level
        else depression.get("label")
        or anxiety.get("label")
    )

    summary = (
        f"Тревога: {anxiety.get('label', 'нет данных')} "
        f"({subscale_scores.get('ANX', 0)} баллов), "
        f"депрессия: {depression.get('label', 'нет данных')} "
        f"({subscale_scores.get('DEP', 0)} баллов)"
    )

    result_json: Dict[str, Any] = {
        "total_score": total_score,
        "summary": summary,
        "subscales": {
            "anxiety": {
                "score": subscale_scores.get("ANX", 0),
                "level": anxiety_level,
                "label": anxiety.get("label"),
            },
            "depression": {
                "score": subscale_scores.get("DEP", 0),
                "level": depression_level,
                "label": depression.get("label"),
            },
        },
        "anxiety_score": subscale_scores.get("ANX"),
        "depression_score": subscale_scores.get("DEP"),
        "anxiety_level": anxiety_level,
        "depression_level": depression_level,
        "total_level": total_level_code,
        "total_label": worst_label,
        "ANX": {
            "score": subscale_scores.get("ANX", 0),
            "level": anxiety_level,
            "label": anxiety.get("label"),
        },
        "DEP": {
            "score": subscale_scores.get("DEP", 0),
            "level": depression_level,
            "label": depression.get("label"),
        },
    }

    return result_json, answers_log
