**Задача:** Модуль рутинной оценки сна (Sleep Tracker) — ежедневный сбор данных о сне у пациентов на программном гемодиализе.

**Дата:** 2026-02-10

**Действия:**
- Создан бэкенд `app/sleep_tracker/`: модели (SleepRecord, схема `sleep`), Pydantic-схемы и enums, сервис (TIB, SE, late_entry, dialysis_day), CRUD, роутер POST/GET `/api/v1/sleep/me`.
- Валидация: TIB с переходом через полночь; SE = TST/TIB×100, hard validation при TST > TIB; late_entry при отправке после 14:00; dialysis_day из расписания диализа по дате отправки.
- Зарегистрированы модуль в `app/models/__init__.py`, роутер и схема `sleep` в `app/main.py`, импорт в `alembic/env.py`.
- Добавлена миграция `20260210_02_sleep_tracker.py`: схема `sleep`, таблица `sleep_records`.
- Добавлена страница пациента `/patient/sleep_tracker`: одноэкранная форма Q1–Q7, time picker (step 15 мин), кнопки выбора, мультивыбор Q7 с «Ничего не мешало», предупреждения TIB и SE, кнопка «Отправить» внизу (активна после заполнения Q1–Q5 и при корректном SE).
- В сайдбар добавлен пункт «Оценка сна» с маршрутом на Sleep Tracker.

**Файлы:**
- Новые: `app/sleep_tracker/__init__.py`, `models.py`, `schemas.py`, `service.py`, `crud.py`, `router.py`; `alembic/versions/20260210_02_sleep_tracker.py`; `frontend/patient/sleep_tracker.html`, `css/sleep_tracker.css`, `js/sleep_tracker.js`.
- Изменены: `app/models/__init__.py`, `app/main.py`, `alembic/env.py`, `app/pages/router.py`, `frontend/patient/js/sidebar.js`, `frontend/patient/components/sidebar.html`.

**Результат:** Пациент может заполнять рутинную оценку сна (время отхода/пробуждения, TST, пробуждения, латентность, самочувствие, дневной сон, причины нарушений). Запись сохраняется с автоматическими полями submitted_at, late_entry, dialysis_day, TIB и SE. Офлайн-режим (локальное сохранение и синхронизация) в текущей реализации не реализован — возможное расширение.

**Проблемы:** Нет.
