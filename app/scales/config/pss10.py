# ============================================
# PSS-10 Config: Шкала воспринимаемого стресса
# ============================================
# 10 вопросов, 5-балльные ответы (0–4), два субшкала.
# ВАЖНО: вопросы 4, 5, 7, 8 — реверсные (4 - raw_value).
# Реверсия применяется в калькуляторе, здесь хранятся сырые значения.

"""Конфигурация шкалы воспринимаемого стресса ШВС-10 (PSS-10)."""

_OPTS = [
    {"text": "Никогда",         "value": 0},
    {"text": "Почти никогда",   "value": 1},
    {"text": "Иногда",          "value": 2},
    {"text": "Довольно часто",  "value": 3},
    {"text": "Очень часто",     "value": 4},
]


def _make_options(question_id: str) -> list:
    return [
        {"id": f"{question_id}_opt{opt['value']}", "text": opt["text"], "value": opt["value"]}
        for opt in _OPTS
    ]


PSS10_CONFIG: dict = {
    "code": "PSS10",
    "version": "1.0",
    "title": "Шкала воспринимаемого стресса ШВС-10",

    "instruction": (
        "Следующие вопросы касаются ваших мыслей и чувств за последний месяц. "
        "В каждом случае укажите, как часто вы чувствовали или думали именно так."
    ),

    "questions": [
        {
            "id": "pss_q1",
            "number": 1,
            "subscale": "perceived_stress",
            "reverse": False,
            "text": "Как часто вас расстраивало что-то неожиданное?",
            "options": _make_options("pss_q1"),
        },
        {
            "id": "pss_q2",
            "number": 2,
            "subscale": "perceived_stress",
            "reverse": False,
            "text": "Как часто вы чувствовали, что не можете контролировать важные вещи в своей жизни?",
            "options": _make_options("pss_q2"),
        },
        {
            "id": "pss_q3",
            "number": 3,
            "subscale": "perceived_stress",
            "reverse": False,
            "text": "Как часто вы чувствовали нервозность и стресс?",
            "options": _make_options("pss_q3"),
        },
        {
            "id": "pss_q4",
            "number": 4,
            "subscale": "perceived_coping",
            "reverse": True,  # РЕВЕРС: 4 - raw_value
            "text": "Как часто вы чувствовали уверенность в своей способности справляться с личными проблемами?",
            "options": _make_options("pss_q4"),
        },
        {
            "id": "pss_q5",
            "number": 5,
            "subscale": "perceived_coping",
            "reverse": True,  # РЕВЕРС: 4 - raw_value
            "text": "Как часто вы чувствовали, что дела идут так, как вам хочется?",
            "options": _make_options("pss_q5"),
        },
        {
            "id": "pss_q6",
            "number": 6,
            "subscale": "perceived_stress",
            "reverse": False,
            "text": "Как часто вы чувствовали, что не можете справиться со всем, что вам нужно сделать?",
            "options": _make_options("pss_q6"),
        },
        {
            "id": "pss_q7",
            "number": 7,
            "subscale": "perceived_coping",
            "reverse": True,  # РЕВЕРС: 4 - raw_value
            "text": "Как часто вы могли контролировать раздражители в своей жизни?",
            "options": _make_options("pss_q7"),
        },
        {
            "id": "pss_q8",
            "number": 8,
            "subscale": "perceived_coping",
            "reverse": True,  # РЕВЕРС: 4 - raw_value
            "text": "Как часто вы чувствовали, что держите всё под контролем?",
            "options": _make_options("pss_q8"),
        },
        {
            "id": "pss_q9",
            "number": 9,
            "subscale": "perceived_stress",
            "reverse": False,
            "text": "Как часто вас злили вещи, которые были вне вашего контроля?",
            "options": _make_options("pss_q9"),
        },
        {
            "id": "pss_q10",
            "number": 10,
            "subscale": "perceived_stress",
            "reverse": False,
            "text": "Как часто вы чувствовали, что трудностей накопилось так много, что их невозможно преодолеть?",
            "options": _make_options("pss_q10"),
        },
    ],

    "thresholds": [
        {"min": 0,  "max": 13, "level": "low",      "label": "Низкий уровень стресса"},
        {"min": 14, "max": 26, "level": "moderate",  "label": "Умеренный уровень стресса"},
        {"min": 27, "max": 40, "level": "high",      "label": "Высокий уровень стресса"},
    ],

    "subscales": {
        "perceived_stress": {
            "description": "Воспринимаемый стресс (прямые вопросы: 1, 2, 3, 6, 9, 10)",
            "questions": ["pss_q1", "pss_q2", "pss_q3", "pss_q6", "pss_q9", "pss_q10"],
            "range": {"min": 0, "max": 24},
        },
        "perceived_coping": {
            "description": "Воспринимаемый контроль/совладание (реверсные вопросы: 4, 5, 7, 8)",
            "questions": ["pss_q4", "pss_q5", "pss_q7", "pss_q8"],
            "range": {"min": 0, "max": 16},
            "note": "Высокий балл = хороший воспринимаемый контроль.",
        },
    },

    "patient_result_texts": {
        "low": "Уровень стресса сейчас невысокий — вы справляетесь с нагрузками.",
        "moderate": (
            "Стресс заметен и влияет на самочувствие. "
            "Модуль «Стресс» и раздел «Распорядок дня» могут помочь найти точки опоры."
        ),
        "high": (
            "Уровень стресса сейчас высокий. "
            "Важно обсудить это с врачом или психологом — не оставайтесь с этим одни."
        ),
    },
}
