from __future__ import annotations

from typing import Any, Dict, List, Union

from app.scales.config.tobol import TOBOL_CONFIG


def calculate_tobol(answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Расчёт шкалы ТОБОЛ на основе статического конфига."""

    types_meta = TOBOL_CONFIG["types_meta"]
    diagnostic_code = TOBOL_CONFIG["diagnostic_code"]
    mapping = TOBOL_CONFIG["question_mapping"]

    type_scores_ru: Dict[str, int] = {code: 0 for code in types_meta.keys()}
    forbidden_ru: set[str] = set()
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

        mapping_row = mapping.get(question_id)
        if not mapping_row:
            raise ValueError(f"Unknown question id: {question_id}")

        topic = mapping_row.get("topic")
        row = mapping_row.get("row")
        topic_block = diagnostic_code.get(topic)
        if topic_block is None:
            raise ValueError(f"Unknown topic in diagnostic code: {topic}")

        row_cfg = topic_block.get(row)
        if row_cfg is None:
            raise ValueError(f"Unknown row {row} for topic {topic}")

        coeffs = row_cfg.get("coeffs", {})
        for t_code, score in coeffs.items():
            type_scores_ru[t_code] += int(score)

        forbidden_ru.update(row_cfg.get("forbid_types", []) or [])

        answers_log.append(
            {
                "question_id": question_id,
                "option_id": option_id,
                "topic": topic,
                "row": row,
                "coeffs": coeffs,
            }
        )

    if not answers:
        raise ValueError("Ответы на шкалу ТОБОЛ не переданы")

    max_score = max(type_scores_ru.values()) if type_scores_ru else 0
    leading_ru = [t for t, score in type_scores_ru.items() if score == max_score and t not in forbidden_ru and score > 0]

    subscales: Dict[str, Dict[str, Any]] = {}
    for ru_code, meta in types_meta.items():
        latin_key = meta["key"]
        subscales[latin_key] = {
            "score": type_scores_ru.get(ru_code, 0),
            "label": meta["label"],
            "adaptive": meta["adaptive"],
        }

    if not leading_ru:
        summary = "Ведущий тип отношения к болезни не выявлен."
    elif len(leading_ru) == 1:
        ru_code = leading_ru[0]
        meta = types_meta[ru_code]
        summary = f"Ведущий тип отношения к болезни: {meta['label']} ({ru_code})."
        if meta.get("adaptive"):
            summary = f"{summary} Профиль в целом ближе к адаптивному."
    else:
        parts = [f"{types_meta[t]['label']} ({t})" for t in leading_ru]
        summary = f"Ведущие типы отношения к болезни: {', '.join(parts)}."

    result_json: Dict[str, Any] = {
        "total_score": max_score,
        "summary": summary,
        "subscales": subscales,
        "raw": {
            "type_scores_ru": type_scores_ru,
            "forbidden_types_ru": sorted(forbidden_ru),
            "leading_types_ru": leading_ru,
        },
    }

    return result_json, answers_log
