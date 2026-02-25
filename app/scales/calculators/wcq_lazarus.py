# ============================================
# WCQ Calculator: Опросник Лазаруса
# ============================================
# 50 пунктов, 8 субшкал, нет глобального балла.
#
# Ключевые правила:
#   1. total_score не используется — только субшкальные суммы.
#   2. Нормализация: normalized = raw / max * 100
#      (субшкалы разного размера: 4, 6 или 8 пунктов).
#   3. adaptive_ratio = mean(adaptive_normalized) / (mean(adaptive) + mean(maladaptive))
#      По инструкции Вассерман 1999: используем mean, а не sum,
#      чтобы не давать преимущество группе с большим числом субшкал.
#   4. ICF d240 пороги: ≥0.65 → 0, 0.45–0.64 → 2, <0.45 → 3
#      (матрица подсчёта wcq_lazarus_scoring_matrix.md).
#   5. Каждая субшкала получает качественный уровень по процентильным нормам.

from __future__ import annotations

from typing import Any, Dict, List, Union

from app.scales.config.wcq_lazarus import WCQ_CONFIG


def calculate_wcq_lazarus(answers: List[Union[Dict[str, str], "ScaleAnswerIn"]]):
    """Считаем результат по опроснику WCQ (Лазарус).

    Принимает список ответов {question_id, option_id}.
    Возвращает (result_json, answers_log).

    result_json содержит:
      - subscales: 8 субшкал с raw, normalized, level, level_label
      - adaptive_ratio: mean-нормализованный индекс адаптивности
      - icf_qualifier / icf_label: для исследователя
      - patient_message: текст благодарности
      - subscale_order: порядок отображения для фронтенда
    """

    questions_map = {q["id"]: q for q in WCQ_CONFIG["questions"]}
    expected_ids = set(questions_map.keys())
    subscale_meta = WCQ_CONFIG["subscale_meta"]
    norms = WCQ_CONFIG["norms"]

    subscale_raw: Dict[str, int] = {sub: 0 for sub in subscale_meta}
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

        option = next((o for o in question["options"] if o["id"] == option_id), None)
        if not option:
            raise ValueError(f"Unknown option id: {option_id} for question {question_id}")

        score_value = int(option["score"])
        subscale = question["subscale"]
        subscale_raw[subscale] += score_value

        answers_log.append({
            "question_id": question_id,
            "option_id": option_id,
            "score_value": score_value,
        })

    # Проверяем полноту ответов
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

    # Нормализация + процентильный уровень по нормам
    subscales_out: Dict[str, Dict[str, Any]] = {}
    for sub_id, raw in subscale_raw.items():
        meta = subscale_meta[sub_id]
        max_possible = meta["max"]
        normalized = round(raw / max_possible * 100, 1)

        sub_norms = norms.get(sub_id, [])
        matched_norm = next((n for n in sub_norms if n["min"] <= raw <= n["max"]), None)
        level = matched_norm["level"] if matched_norm else "unknown"
        level_label = matched_norm["label"] if matched_norm else "—"

        subscales_out[sub_id] = {
            "raw": raw,
            "max": max_possible,
            "normalized": normalized,
            "level": level,
            "level_label": level_label,
            "type": meta["type"],
            "name": meta["name"],
        }

    # adaptive_ratio через mean (по инструкции 1999):
    #   adaptive_mean / (adaptive_mean + maladaptive_mean)
    # Смешанные субшкалы (distancing, accepting_responsibility) не учитываются.
    adaptive_subs = WCQ_CONFIG["adaptive_subscales"]
    maladaptive_subs = WCQ_CONFIG["maladaptive_subscales"]

    adaptive_mean = sum(subscales_out[s]["normalized"] for s in adaptive_subs) / len(adaptive_subs)
    maladaptive_mean = sum(subscales_out[s]["normalized"] for s in maladaptive_subs) / len(maladaptive_subs)
    denom = adaptive_mean + maladaptive_mean
    adaptive_ratio = round(adaptive_mean / denom, 3) if denom > 0 else 0.0

    # ICF d240 квалификатор (пороги из scoring_matrix.md)
    if adaptive_ratio >= 0.65:
        icf_qualifier = 0
        icf_label = "Нет нарушения — преобладает адаптивный копинг"
    elif adaptive_ratio >= 0.45:
        icf_qualifier = 2
        icf_label = "Умеренное нарушение — смешанный репертуар"
    else:
        icf_qualifier = 3
        icf_label = "Тяжёлое нарушение — преобладает дезадаптивный копинг"

    result_json: Dict[str, Any] = {
        # total_score намеренно отсутствует — интерпретация только по субшкалам
        "subscales": subscales_out,
        "subscale_order": WCQ_CONFIG["subscale_order"],
        "adaptive_ratio": adaptive_ratio,
        "icf_qualifier": icf_qualifier,
        "icf_label": icf_label,
        "summary": f"WCQ: адаптивный индекс {adaptive_ratio:.2f} — {icf_label}",
        "patient_message": WCQ_CONFIG["patient_message"],
    }

    return result_json, answers_log
