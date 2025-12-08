from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Tuple, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.scales.config.hads import HADS_CONFIG
from app.scales.config.kop25a import KOP25A_CONFIG, KOP25A_GROUPS
from app.scales.config.tobol import TOBOL_CONFIG
from app.scales.models import ScaleResult


TOBOL_TYPE_MAPPING = {
    "Г": {"code": "G", "label": "Гармоничный", "adaptive": True},
    "Р": {"code": "R", "label": "Эргопатический", "adaptive": True},
    "З": {"code": "Z", "label": "Анозогнозический", "adaptive": False},
    "Т": {"code": "T", "label": "Тревожный", "adaptive": False},
    "И": {"code": "I", "label": "Ипохондрический", "adaptive": False},
    "Н": {"code": "N", "label": "Неврастенический", "adaptive": False},
    "М": {"code": "M", "label": "Меланхолический", "adaptive": False},
    "А": {"code": "A", "label": "Апатический", "adaptive": False},
    "С": {"code": "S", "label": "Сенситивный", "adaptive": False},
    "Э": {"code": "E", "label": "Эгоцентрический", "adaptive": False},
    "П": {"code": "P", "label": "Паранойяльный", "adaptive": False},
    "Д": {"code": "D", "label": "Дисфорический", "adaptive": False},
}

TOBOL_RU_NORMALIZATION = {
    "M": "М",
    "A": "А",
    "P": "Р",
    "C": "С",
    "E": "Э",
}


def get_scale_config(scale_code: str) -> dict:
    """Возвращаем конфиг шкалы по её коду."""

    code = scale_code.upper()
    if code == "HADS":
        return HADS_CONFIG
    if code == "KOP25A":
        return KOP25A_CONFIG
    if code == "TOBOL":
        return TOBOL_CONFIG
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

    # применяем cutoffs и формируем результат по субшкалам
    subscales: Dict[str, Dict[str, Any]] = {}
    cutoffs = scale_config.get("cutoffs", {})
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

    # Определяем общий уровень по наихудшему из субшкал
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
    # Формируем компактное представление: итоговый балл + текстовая сводка для фронта.
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
        # Дополнительные поля для совместимости с существующими потребителями API.
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


def calculate_kop25a_result(
    scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """Подсчёт показателей приверженности для шкалы КОП-25 А1."""

    questions_map = {question["id"]: question for question in scale_config.get("questions", [])}
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


def _parse_tobol_question_id(question_id: str) -> Tuple[str, str]:
    if "_" not in question_id:
        raise ValueError(
            "Некорректный идентификатор вопроса. Ожидался формат 'I_1', 'II_3' и т.п."
        )
    section, item = question_id.split("_", 1)
    section = section.replace(".", "")
    return section, item


def _build_tobol_summary(leading: List[str]) -> str:
    if not leading:
        return "Недостаточно данных для определения ведущего типа отношения к болезни."

    titles = [f"{TOBOL_TYPE_MAPPING[t]['label']} ({t})" for t in leading]

    if len(leading) == 1:
        code = leading[0]
        title = TOBOL_TYPE_MAPPING[code]["label"]
        if code in {"Г", "Р", "З"}:
            prefix = "Преобладает адаптивный тип отношения к болезни"
        else:
            prefix = "Преобладает неадаптивный тип отношения к болезни"
        return f"{prefix}: {title} ({code})."

    return f"Выявлены смешанные типы отношения к болезни: {', '.join(titles)}."


def calculate_tobol_result(
    scale_config: dict, answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    diagnostic_code: Dict[str, Dict[str, dict]] = scale_config.get("diagnostic_code", {})
    if not diagnostic_code:
        raise ValueError("Диагностический код ТОБОЛ не найден в конфиге")

    expected_ids = {
        f"{section}_{item_id}" for section, items in diagnostic_code.items() for item_id in items.keys()
    }

    type_scores: Dict[str, int] = {key: 0 for key in TOBOL_TYPE_MAPPING.keys()}
    forbidden: set[str] = set()
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

        section, item_from_id = _parse_tobol_question_id(question_id)
        if question_id not in expected_ids:
            raise ValueError(f"Unknown question id: {question_id}")
        item_code = str(option_id or item_from_id)

        section_block = diagnostic_code.get(section)
        if not section_block:
            raise ValueError(f"Unknown section in question id: {section}")

        row = section_block.get(item_from_id) or section_block.get(item_code)
        if not row:
            raise ValueError(f"Unknown option id: {option_id} for question {question_id}")

        coeffs: Dict[str, int] = row.get("coeffs", {})
        for t_code, score in coeffs.items():
            normalized_code = t_code
            if normalized_code not in type_scores:
                normalized_code = TOBOL_RU_NORMALIZATION.get(t_code, t_code)
            if normalized_code not in type_scores:
                continue
            type_scores[normalized_code] += int(score)

        forbidden.update(row.get("forbid_types", []) or [])

        answers_log.append(
            {
                "question_id": question_id,
                "option_id": option_id,
                "section": section,
                "code_row": item_from_id,
                "coeffs": coeffs,
            }
        )

    if not answers:
        raise ValueError("Ответы на шкалу ТОБОЛ не переданы")

    max_score = max(type_scores.values()) if type_scores else 0
    leading_types = [t for t, score in type_scores.items() if score == max_score and t not in forbidden and score > 0]

    subscales = {
        data["code"]: {
            "score": type_scores.get(ru_code, 0),
            "label": data["label"],
            "adaptive": data["adaptive"],
        }
        for ru_code, data in TOBOL_TYPE_MAPPING.items()
    }

    summary = _build_tobol_summary(leading_types)

    result_json: Dict[str, Any] = {
        "total_score": max_score,
        "summary": summary,
        "subscales": subscales,
        "raw": {
            "type_scores_ru": type_scores,
            "forbidden_types_ru": sorted(forbidden),
            "leading_types_ru": leading_types,
        },
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
