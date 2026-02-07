"""Калькулятор Питтсбургского опросника качества сна (PSQI).

Принимает «сырые» ответы из фронтенда, валидирует и возвращает
(result_json, answers_log).
"""

from __future__ import annotations

from typing import Any, Dict, List, Union


def _parse_time_to_hours(time_str: str) -> float:
    """Парсит строку 'HH:MM' в дробное число часов."""
    parts = time_str.strip().split(":")
    if len(parts) != 2:
        raise ValueError(f"Неверный формат времени: {time_str}. Ожидается ЧЧ:ММ")
    
    try:
        h, m = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"Неверный формат времени: {time_str}. Часы и минуты должны быть числами")
    
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Время вне допустимого диапазона: {time_str}")
    return h + m / 60.0


def _time_in_bed_hours(bedtime_str: str, waketime_str: str) -> float:
    """Рассчитывает время в постели (часы) с учётом перехода через полночь.
    
    Добавляет валидацию: время в постели должно быть в разумных пределах (3-18 часов).
    """
    bed = _parse_time_to_hours(bedtime_str)
    wake = _parse_time_to_hours(waketime_str)
    diff = wake - bed
    if diff <= 0:
        diff += 24
    
    # Валидируем разумность результата
    if diff < 3 or diff > 18:
        raise ValueError(
            f"Время в постели вне разумного диапазона: {round(diff, 1)} часов. "
            f"Ожидается от 3 до 18 часов. Проверьте время отхода ко сну ({bedtime_str}) "
            f"и время подъёма ({waketime_str})"
        )
    
    return diff


def _get_answer(answers: dict, key: str, *, required: bool = True) -> Any:
    """Достаёт значение из словаря ответов."""
    val = answers.get(key)
    if required and val is None:
        raise ValueError(f"Отсутствует обязательный ответ: {key}")
    return val


def calculate_psqi(
    answers: List[Union[Dict[str, Any], Any]],
) -> tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    Рассчитывает 7 компонентов PSQI и глобальный балл.

    Ожидает список ответов вида:
      [{"question_id": "q1", "value": "23:30"}, {"question_id": "q5a", "value": 2}, ...]

    Возвращает (result_json, answers_log).
    """

    # --- нормализуем ответы в dict: question_id -> value ---
    raw: Dict[str, Any] = {}
    answers_log: List[Dict[str, Any]] = []

    for ans in answers:
        if isinstance(ans, dict):
            qid = ans.get("question_id")
            val = ans.get("value")
        else:
            qid = getattr(ans, "question_id", None)
            val = getattr(ans, "value", None)

        if qid is None:
            raise ValueError("Ответ без question_id")

        if qid in raw:
            raise ValueError(f"Дублирующийся ответ для {qid}")

        raw[qid] = val
        answers_log.append({"question_id": qid, "value": val})

    # --- извлекаем значения ---
    q1 = str(_get_answer(raw, "q1"))           # время отхода ко сну (HH:MM)
    q2 = float(_get_answer(raw, "q2"))          # минуты до засыпания
    q3 = str(_get_answer(raw, "q3"))            # время подъёма (HH:MM)
    q4 = float(_get_answer(raw, "q4"))          # часы сна

    q5a = int(_get_answer(raw, "q5a"))
    q5b = int(_get_answer(raw, "q5b"))
    q5c = int(_get_answer(raw, "q5c"))
    q5d = int(_get_answer(raw, "q5d"))
    q5e = int(_get_answer(raw, "q5e"))
    q5f = int(_get_answer(raw, "q5f"))
    q5g = int(_get_answer(raw, "q5g"))
    q5h = int(_get_answer(raw, "q5h"))
    q5i = int(_get_answer(raw, "q5i"))
    q5j = int(_get_answer(raw, "q5j"))

    q6 = int(_get_answer(raw, "q6"))
    q7 = int(_get_answer(raw, "q7"))
    q8 = int(_get_answer(raw, "q8"))
    q9 = int(_get_answer(raw, "q9"))
    q10 = int(_get_answer(raw, "q10"))

    # q11 (опционально — зависит от q10)
    # Если у пациента есть партнёр/сосед (q10 = 2 или 3), вопросы q11 должны быть заполнены
    if q10 in (2, 3):
        q11a = int(_get_answer(raw, "q11a", required=True))
        q11b = int(_get_answer(raw, "q11b", required=True))
        q11c = int(_get_answer(raw, "q11c", required=True))
        q11d = int(_get_answer(raw, "q11d", required=True))
        q11e = int(_get_answer(raw, "q11e", required=True))
    else:
        # Вопросы q11 опциональны (по умолчанию 0)
        q11a = int(raw.get("q11a", 0))
        q11b = int(raw.get("q11b", 0))
        q11c = int(raw.get("q11c", 0))
        q11d = int(raw.get("q11d", 0))
        q11e = int(raw.get("q11e", 0))

    # текстовые поля (не входят в расчёт, но сохраняем)
    q5j_text = raw.get("q5j_text", "")
    q11e_text = raw.get("q11e_text", "")

    # ===================== РАСЧЁТ КОМПОНЕНТОВ =====================

    # КОМПОНЕНТ 1: Субъективное качество сна = q6 (0-3)
    component1 = q6

    # КОМПОНЕНТ 2: Латентность сна
    if q2 <= 15:
        q2_score = 0
    elif 16 <= q2 <= 30:
        q2_score = 1
    elif 31 <= q2 <= 60:
        q2_score = 2
    else:  # > 60
        q2_score = 3

    c2_sum = q2_score + q5a
    if c2_sum == 0:
        component2 = 0
    elif c2_sum <= 2:
        component2 = 1
    elif c2_sum <= 4:
        component2 = 2
    else:
        component2 = 3

    # КОМПОНЕНТ 3: Длительность сна (q4)
    if q4 > 7:
        component3 = 0
    elif q4 >= 6:
        component3 = 1
    elif q4 >= 5:
        component3 = 2
    else:
        component3 = 3

    # КОМПОНЕНТ 4: Эффективность сна
    time_in_bed = _time_in_bed_hours(q1, q3)
    if time_in_bed <= 0:
        efficiency = 0.0
    else:
        efficiency = (q4 / time_in_bed) * 100

    if efficiency > 85:
        component4 = 0
    elif efficiency >= 75:
        component4 = 1
    elif efficiency >= 65:
        component4 = 2
    else:
        component4 = 3

    # КОМПОНЕНТ 5: Нарушения сна (q5b-q5j, без q5a)
    c5_sum = q5b + q5c + q5d + q5e + q5f + q5g + q5h + q5i + q5j
    if c5_sum == 0:
        component5 = 0
    elif c5_sum <= 9:
        component5 = 1
    elif c5_sum <= 18:
        component5 = 2
    else:
        component5 = 3

    # КОМПОНЕНТ 6: Использование снотворных = q7 (0-3)
    component6 = q7

    # КОМПОНЕНТ 7: Дневная дисфункция
    c7_sum = q8 + q9
    if c7_sum == 0:
        component7 = 0
    elif c7_sum <= 2:
        component7 = 1
    elif c7_sum <= 4:
        component7 = 2
    else:
        component7 = 3

    # ГЛОБАЛЬНЫЙ БАЛЛ
    global_score = (
        component1 + component2 + component3 + component4
        + component5 + component6 + component7
    )

    # ===================== ИНТЕРПРЕТАЦИЯ =====================
    if global_score <= 5:
        level = "normal"
        label = "Нормальное качество сна"
    elif global_score <= 10:
        level = "moderate"
        label = "Умеренные нарушения сна"
    elif global_score <= 15:
        level = "significant"
        label = "Значительные нарушения сна"
    else:
        level = "severe"
        label = "Выраженные нарушения сна"

    summary = f"PSQI: {global_score} баллов — {label}"

    # ===================== КЛИНИЧЕСКИЕ ФЛАГИ (q11) =====================
    clinical_flags: List[Dict[str, str]] = []
    if q10 in (2, 3):
        if q11a >= 2 or q11b >= 1:
            clinical_flags.append({
                "id": "apnea_risk",
                "name": "Подозрение на обструктивное апноэ сна",
                "recommendation": "Рассмотреть направление на полисомнографию",
            })
        if q11c >= 2:
            clinical_flags.append({
                "id": "rls_risk",
                "name": "Подозрение на синдром беспокойных ног",
                "recommendation": "Дополнительный скрининг (шкала IRLS)",
            })
        if q11d >= 1:
            clinical_flags.append({
                "id": "parasomnia_risk",
                "name": "Подозрение на парасомнии",
                "recommendation": "Консультация сомнолога",
            })

    # ===================== RESULT JSON =====================
    result_json: Dict[str, Any] = {
        "total_score": global_score,
        "summary": summary,
        "level": level,
        "label": label,
        "components": {
            "C1_subjective_quality": component1,
            "C2_sleep_latency": component2,
            "C3_sleep_duration": component3,
            "C4_sleep_efficiency": component4,
            "C5_sleep_disturbances": component5,
            "C6_sleep_medication": component6,
            "C7_daytime_dysfunction": component7,
        },
        "details": {
            "bedtime": q1,
            "wake_time": q3,
            "sleep_latency_min": q2,
            "sleep_duration_hours": q4,
            "time_in_bed_hours": round(time_in_bed, 2),
            "sleep_efficiency_pct": round(efficiency, 1),
        },
        "clinical_flags": clinical_flags,
        "q10_partner": q10,
    }

    if q5j_text:
        result_json["q5j_other_reason"] = q5j_text
    if q11e_text:
        result_json["q11e_other_concern"] = q11e_text

    return result_json, answers_log
