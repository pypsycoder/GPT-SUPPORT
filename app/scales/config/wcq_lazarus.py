# ============================================
# WCQ Config: Опросник Лазаруса (Ways of Coping Questionnaire)
# ============================================
# 50 пунктов, 8 субшкал. Глобальный балл не используется.
# Нормализация: normalized = raw / max * 100
# Нормы: СПб НИПНИ им. Бехтерева, популяционная выборка n=200.

"""Конфигурация опросника совладающего поведения WCQ (Лазарус)."""

# --- Сырые данные вопросов: (номер, субшкала, текст) ---
_QUESTIONS_RAW = [
    (1,  "planful_problem_solving",  "...сосредотачивался на том, что мне нужно было делать дальше — на следующем шаге"),
    (2,  "confrontive_coping",       "...начинал что-то делать, зная, что это всё равно не будет работать, главное — делать хоть что-нибудь"),
    (3,  "confrontive_coping",       "...пытался склонить вышестоящих к тому, чтобы они изменили своё мнение"),
    (4,  "seeking_social_support",   "...говорил с другими, чтобы больше узнать о ситуации"),
    (5,  "accepting_responsibility", "...критиковал и укорял себя"),
    (6,  "self_control",             "...пытался не сжигать за собой мосты, оставляя всё, как оно есть"),
    (7,  "escape_avoidance",         "...надеялся на чудо"),
    (8,  "distancing",               "...смирялся с судьбой: бывает, что мне не везёт"),
    (9,  "distancing",               "...вёл себя, как будто ничего не произошло"),
    (10, "self_control",             "...старался не показывать своих чувств"),
    (11, "distancing",               "...пытался увидеть в ситуации что-то положительное"),
    (12, "escape_avoidance",         "...спал больше обычного"),
    (13, "confrontive_coping",       "...срывал свою досаду на тех, кто навлёк на меня проблемы"),
    (14, "seeking_social_support",   "...искал сочувствия и понимания у кого-нибудь"),
    (15, "positive_reappraisal",     "...во мне возникла потребность выразить себя творчески"),
    (16, "distancing",               "...пытался забыть всё это"),
    (17, "seeking_social_support",   "...обращался за помощью к специалистам"),
    (18, "positive_reappraisal",     "...менялся или рос как личность в положительную сторону"),
    (19, "accepting_responsibility", "...извинялся или старался всё загладить"),
    (20, "planful_problem_solving",  "...составлял план действий"),
    (21, "confrontive_coping",       "...старался дать какой-то выход своим чувствам"),
    (22, "accepting_responsibility", "...понимал, что сам вызвал эту проблему"),
    (23, "positive_reappraisal",     "...набирался опыта в этой ситуации"),
    (24, "seeking_social_support",   "...говорил с кем-либо, кто мог конкретно помочь в этой ситуации"),
    (25, "escape_avoidance",         "...пытался улучшить своё самочувствие едой, выпивкой, курением или лекарствами"),
    (26, "confrontive_coping",       "...рисковал напропалую"),
    (27, "self_control",             "...старался действовать не слишком поспешно, доверяясь первому порыву"),
    (28, "positive_reappraisal",     "...находил новую веру во что-то"),
    (29, "positive_reappraisal",     "...вновь открывал для себя что-то важное"),
    (30, "planful_problem_solving",  "...что-то менял так, что всё улаживалось"),
    (31, "escape_avoidance",         "...в целом избегал общения с людьми"),
    (32, "distancing",               "...не допускал это до себя, стараясь об этом особенно не задумываться"),
    (33, "seeking_social_support",   "...спрашивал совета у родственника или друга, которых уважал"),
    (34, "self_control",             "...старался, чтобы другие не узнали, как плохо обстоят дела"),
    (35, "distancing",               "...отказывался воспринимать это слишком серьёзно"),
    (36, "seeking_social_support",   "...говорил о том, что я чувствую"),
    (37, "confrontive_coping",       "...стоял на своём и боролся за то, чего хотел"),
    (38, "escape_avoidance",         "...вымещал это на других людях"),
    (39, "planful_problem_solving",  "...пользовался прошлым опытом — мне приходилось уже попадать в такие ситуации"),
    (40, "planful_problem_solving",  "...знал, что надо делать, и удваивал свои усилия, чтобы всё наладить"),
    (41, "escape_avoidance",         "...отказывался верить, что это действительно произошло"),
    (42, "accepting_responsibility", "...давал обещание, что в следующий раз всё будет по-другому"),
    (43, "planful_problem_solving",  "...находил пару других способов решения проблемы"),
    (44, "self_control",             "...старался, чтобы мои эмоции не слишком мешали мне в других делах"),
    (45, "positive_reappraisal",     "...что-то менял в себе"),
    (46, "escape_avoidance",         "...хотел, чтобы всё это скорее как-то образовалось или кончилось"),
    (47, "escape_avoidance",         "...представлял себе, фантазировал, как всё это могло бы обернуться"),
    (48, "positive_reappraisal",     "...молился"),
    (49, "self_control",             "...прокручивал в уме, что мне сказать или сделать"),
    (50, "positive_reappraisal",     "...думал о том, как бы в данной ситуации действовал человек, которым я восхищаюсь, и старался подражать ему"),
]

_RESPONSE_LABELS = [
    (0, "Никогда"),
    (1, "Редко"),
    (2, "Иногда"),
    (3, "Часто"),
]

_questions = []
for _n, _subscale, _text in _QUESTIONS_RAW:
    _options = [
        {"id": f"wcq_q{_n}_{_v}", "text": _label, "score": _v}
        for _v, _label in _RESPONSE_LABELS
    ]
    _questions.append({
        "id": f"wcq_q{_n}",
        "subscale": _subscale,
        "text": _text,
        "options": _options,
    })


# Метаданные субшкал: максимальный сырой балл и тип (для нормализации и adaptive_ratio)
WCQ_SUBSCALE_META: dict = {
    "confrontive_coping":      {"max": 18, "type": "maladaptive", "name": "Конфронтационный копинг"},
    "distancing":              {"max": 18, "type": "mixed",       "name": "Дистанцирование"},
    "self_control":            {"max": 18, "type": "adaptive",    "name": "Самоконтроль"},
    "seeking_social_support":  {"max": 18, "type": "adaptive",    "name": "Поиск социальной поддержки"},
    "accepting_responsibility":{"max": 12, "type": "mixed",       "name": "Принятие ответственности"},
    "escape_avoidance":        {"max": 24, "type": "maladaptive", "name": "Бегство-избегание"},
    "planful_problem_solving": {"max": 18, "type": "adaptive",    "name": "Планомерное решение проблем"},
    "positive_reappraisal":    {"max": 24, "type": "adaptive",    "name": "Положительная переоценка"},
}

# Порядок отображения субшкал в результатах
WCQ_SUBSCALE_ORDER = [
    "confrontive_coping",
    "distancing",
    "self_control",
    "seeking_social_support",
    "accepting_responsibility",
    "escape_avoidance",
    "planful_problem_solving",
    "positive_reappraisal",
]

# Процентильные нормы (СПб НИПНИ, n=200, здоровая популяция).
# Источник: Вассерман Л.И. и др., 1999.
# ⚠️ Для ГД-пациентов используются как ориентир, а не клинический стандарт.
WCQ_NORMS: dict = {
    "confrontive_coping": [
        {"min": 0,  "max": 3,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 4,  "max": 5,  "level": "low",        "label": "Низкий"},
        {"min": 6,  "max": 8,  "level": "medium",     "label": "Средний"},
        {"min": 9,  "max": 11, "level": "high",       "label": "Высокий"},
        {"min": 12, "max": 18, "level": "very_high",  "label": "Очень высокий"},
    ],
    "distancing": [
        {"min": 0,  "max": 4,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 5,  "max": 6,  "level": "low",        "label": "Низкий"},
        {"min": 7,  "max": 9,  "level": "medium",     "label": "Средний"},
        {"min": 10, "max": 11, "level": "high",       "label": "Высокий"},
        {"min": 12, "max": 18, "level": "very_high",  "label": "Очень высокий"},
    ],
    "self_control": [
        {"min": 0,  "max": 5,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 6,  "max": 7,  "level": "low",        "label": "Низкий"},
        {"min": 8,  "max": 11, "level": "medium",     "label": "Средний"},
        {"min": 12, "max": 13, "level": "high",       "label": "Высокий"},
        {"min": 14, "max": 18, "level": "very_high",  "label": "Очень высокий"},
    ],
    "seeking_social_support": [
        {"min": 0,  "max": 4,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 5,  "max": 6,  "level": "low",        "label": "Низкий"},
        {"min": 7,  "max": 10, "level": "medium",     "label": "Средний"},
        {"min": 11, "max": 12, "level": "high",       "label": "Высокий"},
        {"min": 13, "max": 18, "level": "very_high",  "label": "Очень высокий"},
    ],
    "accepting_responsibility": [
        {"min": 0,  "max": 2,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 3,  "max": 3,  "level": "low",        "label": "Низкий"},
        {"min": 4,  "max": 6,  "level": "medium",     "label": "Средний"},
        {"min": 7,  "max": 8,  "level": "high",       "label": "Высокий"},
        {"min": 9,  "max": 12, "level": "very_high",  "label": "Очень высокий"},
    ],
    "escape_avoidance": [
        {"min": 0,  "max": 5,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 6,  "max": 7,  "level": "low",        "label": "Низкий"},
        {"min": 8,  "max": 12, "level": "medium",     "label": "Средний"},
        {"min": 13, "max": 15, "level": "high",       "label": "Высокий"},
        {"min": 16, "max": 24, "level": "very_high",  "label": "Очень высокий"},
    ],
    "planful_problem_solving": [
        {"min": 0,  "max": 4,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 5,  "max": 7,  "level": "low",        "label": "Низкий"},
        {"min": 8,  "max": 11, "level": "medium",     "label": "Средний"},
        {"min": 12, "max": 13, "level": "high",       "label": "Высокий"},
        {"min": 14, "max": 18, "level": "very_high",  "label": "Очень высокий"},
    ],
    "positive_reappraisal": [
        {"min": 0,  "max": 5,  "level": "very_low",  "label": "Очень низкий"},
        {"min": 6,  "max": 7,  "level": "low",        "label": "Низкий"},
        {"min": 8,  "max": 12, "level": "medium",     "label": "Средний"},
        {"min": 13, "max": 15, "level": "high",       "label": "Высокий"},
        {"min": 16, "max": 24, "level": "very_high",  "label": "Очень высокий"},
    ],
}

WCQ_CONFIG: dict = {
    "code": "WCQ_LAZARUS",
    "version": "1.0",
    "title": "Опросник способов совладающего поведения (WCQ, Лазарус)",
    "instruction": (
        "Вспомните какую-нибудь трудную ситуацию из вашей жизни за последнее время. "
        "Оцените, как часто вы используете каждый из способов поведения в подобных ситуациях."
    ),
    "period_label": "Оказавшись в трудной ситуации, я...",
    "questions": _questions,
    "subscale_meta": WCQ_SUBSCALE_META,
    "subscale_order": WCQ_SUBSCALE_ORDER,
    "norms": WCQ_NORMS,
    # Субшкалы по типу (для adaptive_ratio)
    "adaptive_subscales":    ["self_control", "seeking_social_support",
                               "planful_problem_solving", "positive_reappraisal"],
    "maladaptive_subscales": ["confrontive_coping", "escape_avoidance"],
    "mixed_subscales":       ["distancing", "accepting_responsibility"],
    "patient_message": (
        "Спасибо за то, что прошли опросник. "
        "Ниже — ваш профиль: насколько часто вы используете каждую стратегию совладания с трудными ситуациями."
    ),
}
