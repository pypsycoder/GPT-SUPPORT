# ============================================
# KOP-25A1 Calculator: Расчёт приверженности лечению
# ============================================
# Суммирует баллы по 5 группам копинг-стратегий,
# определяет уровень приверженности (высокий/средний/низкий).

from __future__ import annotations

from typing import Any, Dict, List, Union

from app.scales.config.kop_25a1 import KOP25A_CONFIG, KOP25A_GROUPS


def calculate_kop_25a1(answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Подсчёт показателей приверженности для шкалы КОП-25 А1."""

    questions_map = {question["id"]: question for question in KOP25A_CONFIG.get("questions", [])}
    expected_ids = set(questions_map.keys())

    answers_log: List[Dict[str, Any]] = []
    seen_questions: set[str] = set()
    question_scores: Dict[str, int] = {}

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
        question_scores[question_id] = score_value

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

    technical_scores: Dict[str, int] = {}
    for group_id, question_ids in KOP25A_GROUPS.items():
        try:
            technical_scores[group_id] = sum(question_scores[qid] for qid in question_ids)
        except KeyError as exc:
            raise ValueError(f"Missing answer for question {exc.args[0]} in group {group_id}") from exc

    vt = technical_scores.get("VT", 0)
    vs = technical_scores.get("VS", 0)
    vm = technical_scores.get("VM", 0)
    gt = technical_scores.get("GT", 0)
    gs = technical_scores.get("GS", 0)
    gm = technical_scores.get("GM", 0)

    pt = 200 / ((30 / vt) * (60 / gt))
    ps = 200 / ((30 / vs) * (60 / gs))
    pm = 200 / ((30 / vm) * (60 / gm))
    pl = (ps + 2 * pm + 3 * pt) / 6

    result_json: Dict[str, Any] = {
        "technical": {
            "VT": vt,
            "VS": vs,
            "VM": vm,
            "GT": gt,
            "GS": gs,
            "GM": gm,
        },
        "adherence": {
            "PT": round(pt, 1),
            "PS": round(ps, 1),
            "PM": round(pm, 1),
            "PL": round(pl, 1),
        },
    }

    adherence_level = "high"
    adherence_label = "Высокая приверженность"
    if pl < 50:
        adherence_level = "low"
        adherence_label = "Низкая приверженность"
    elif pl < 75:
        adherence_level = "moderate"
        adherence_label = "Умеренная приверженность"

    summary = f"{adherence_label}. Итоговый индекс: {round(pl, 1)}%."

    result_json.update(
        {
            "total_score": round(pl, 1),
            "adherence_level": adherence_level,
            "adherence_label": adherence_label,
            "summary": summary,
        }
    )

    return result_json, answers_log
