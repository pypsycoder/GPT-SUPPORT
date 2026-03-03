"""
Справочник бейджей достижений.

level: 1=серый(начало), 2=синий(неделя), 3=зелёный(2 недели),
       4=зелёный+(3 недели), 5=золотой(месяц)
"""

from __future__ import annotations

BADGE_DEFINITIONS: dict[str, dict] = {

    # ── 💊 Лекарства ──────────────────────────────────────────────────────────
    "med_start":   {"icon": "💊", "color": "gray",  "level": 1, "name": "Начало",
                    "desc": "Первая отметка лекарства",      "tracker": "medications"},
    "med_week":    {"icon": "💊", "color": "blue",  "level": 2, "name": "Неделя",
                    "desc": "5 из 7 дней — лекарства",       "tracker": "medications"},
    "med_2weeks":  {"icon": "💊", "color": "green", "level": 3, "name": "Две недели",
                    "desc": "10 из 14 дней — лекарства",     "tracker": "medications"},
    "med_3weeks":  {"icon": "💊", "color": "green", "level": 4, "name": "Три недели",
                    "desc": "15 из 21 дня — лекарства",      "tracker": "medications"},
    "med_month":   {"icon": "💊", "color": "gold",  "level": 5, "name": "Надёжная рука",
                    "desc": "22 из 30 дней — лекарства",     "tracker": "medications"},

    # ── 😴 Сон ────────────────────────────────────────────────────────────────
    "sleep_start":  {"icon": "😴", "color": "gray",  "level": 1, "name": "Первая запись",
                     "desc": "Первая запись сна",             "tracker": "sleep"},
    "sleep_week":   {"icon": "😴", "color": "blue",  "level": 2, "name": "Неделя",
                     "desc": "5 из 7 дней — сон",             "tracker": "sleep"},
    "sleep_2weeks": {"icon": "😴", "color": "green", "level": 3, "name": "Две недели",
                     "desc": "10 из 14 дней — сон",           "tracker": "sleep"},
    "sleep_3weeks": {"icon": "😴", "color": "green", "level": 4, "name": "Три недели",
                     "desc": "15 из 21 дня — сон",            "tracker": "sleep"},
    "sleep_month":  {"icon": "😴", "color": "gold",  "level": 5, "name": "Знаю свой сон",
                     "desc": "22 из 30 дней — сон",           "tracker": "sleep"},

    # ── 📊 Витальные ──────────────────────────────────────────────────────────
    "vitals_start":  {"icon": "📊", "color": "gray",  "level": 1, "name": "Первый замер",
                      "desc": "Первая запись показателей",     "tracker": "vitals"},
    "vitals_week":   {"icon": "📊", "color": "blue",  "level": 2, "name": "Неделя",
                      "desc": "5 из 7 дней — показатели",     "tracker": "vitals"},
    "vitals_2weeks": {"icon": "📊", "color": "green", "level": 3, "name": "Две недели",
                      "desc": "10 из 14 дней — показатели",   "tracker": "vitals"},
    "vitals_3weeks": {"icon": "📊", "color": "green", "level": 4, "name": "Три недели",
                      "desc": "15 из 21 дня — показатели",    "tracker": "vitals"},
    "vitals_month":  {"icon": "📊", "color": "gold",  "level": 5, "name": "Держу руку на пульсе",
                      "desc": "22 из 30 дней — показатели",   "tracker": "vitals"},
    "vitals_full":   {"icon": "💡", "color": "blue",  "level": 2, "name": "Полная картина",
                      "desc": "Все 4 показателя за один день", "tracker": "vitals"},

    # ── 🧘 Практики ───────────────────────────────────────────────────────────
    "practice_start":  {"icon": "🧘", "color": "gray",  "level": 1, "name": "Первая практика",
                        "desc": "Первое выполнение практики",  "tracker": "practices"},
    "practice_week":   {"icon": "🧘", "color": "blue",  "level": 2, "name": "Неделя",
                        "desc": "5 из 7 дней — практики",      "tracker": "practices"},
    "practice_2weeks": {"icon": "🧘", "color": "green", "level": 3, "name": "Две недели",
                        "desc": "10 из 14 дней — практики",    "tracker": "practices"},
    "practice_3weeks": {"icon": "🧘", "color": "green", "level": 4, "name": "Три недели",
                        "desc": "15 из 21 дня — практики",     "tracker": "practices"},
    "practice_month":  {"icon": "🧘", "color": "gold",  "level": 5, "name": "Моя опора",
                        "desc": "22 из 30 дней — практики",    "tracker": "practices"},
    "practice_5":      {"icon": "🧘", "color": "blue",  "level": 2, "name": "Пробую",
                        "desc": "Выполнено 5 разных практик",  "tracker": "practices"},
    "practice_all":    {"icon": "⭐", "color": "gold",  "level": 5, "name": "Исследователь",
                        "desc": "Выполнены все 9 практик",     "tracker": "practices"},

    # ── 📚 Обучение ───────────────────────────────────────────────────────────
    "lesson_first":  {"icon": "📖", "color": "blue",  "level": 2, "name": "Хочу понимать",
                      "desc": "Первый урок пройден",           "tracker": "education"},
    "psych_block":   {"icon": "🧠", "color": "green", "level": 3, "name": "Психологический блок",
                      "desc": "Все 9 модулей блока А",         "tracker": "education"},
    "nephro_block":  {"icon": "🫀", "color": "green", "level": 3, "name": "Жизнь с диализом",
                      "desc": "Все 9 модулей блока Б",         "tracker": "education"},
    "all_lessons":   {"icon": "⭐", "color": "gold",  "level": 5, "name": "Всё прочитал",
                      "desc": "Все 18 модулей пройдены",       "tracker": "education"},

    # ── 📋 Шкалы ──────────────────────────────────────────────────────────────
    "scale_first":   {"icon": "📋", "color": "blue",  "level": 2, "name": "Честный разговор",
                      "desc": "Первая шкала заполнена",        "tracker": "scales"},
    "scale_t0":      {"icon": "🤝", "color": "green", "level": 3, "name": "Участник",
                      "desc": "Все шкалы T0 заполнены",        "tracker": "scales"},
}

# Цвета для CSS-рендера
BADGE_COLORS: dict[str, dict] = {
    "gray":  {"border": "#cccccc", "label": "Начало"},
    "blue":  {"border": "#5B9BD5", "label": "Уровень 2"},
    "green": {"border": "#4AADAD", "label": "Уровень 3"},
    "gold":  {"border": "#E8A020", "label": "Высший уровень"},
}

# Прогрессии серийных бейджей (для точек и модалки)
TRACKER_PROGRESSIONS: dict[str, list[dict]] = {
    "medications": [
        {"key": "med_start",  "label": "Первая отметка"},
        {"key": "med_week",   "label": "5 из 7 дней"},
        {"key": "med_2weeks", "label": "10 из 14 дней"},
        {"key": "med_3weeks", "label": "15 из 21 дня"},
        {"key": "med_month",  "label": "22 из 30 дней"},
    ],
    "sleep": [
        {"key": "sleep_start",  "label": "Первая запись"},
        {"key": "sleep_week",   "label": "5 из 7 дней"},
        {"key": "sleep_2weeks", "label": "10 из 14 дней"},
        {"key": "sleep_3weeks", "label": "15 из 21 дня"},
        {"key": "sleep_month",  "label": "22 из 30 дней"},
    ],
    "vitals": [
        {"key": "vitals_start",  "label": "Первый замер"},
        {"key": "vitals_week",   "label": "5 из 7 дней"},
        {"key": "vitals_2weeks", "label": "10 из 14 дней"},
        {"key": "vitals_3weeks", "label": "15 из 21 дня"},
        {"key": "vitals_month",  "label": "22 из 30 дней"},
    ],
    "practices": [
        {"key": "practice_start",  "label": "Первая практика"},
        {"key": "practice_week",   "label": "5 из 7 дней"},
        {"key": "practice_2weeks", "label": "10 из 14 дней"},
        {"key": "practice_3weeks", "label": "15 из 21 дня"},
        {"key": "practice_month",  "label": "22 из 30 дней"},
    ],
}
