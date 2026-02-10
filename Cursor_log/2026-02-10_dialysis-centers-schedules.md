**Задача:** Реализация модуля «Центры и расписание диализа» по ТЗ.

**Дата:** 2026-02-10

**Действия:**
- Добавлены модели Center и DialysisSchedule, поле center_id в User; зарегистрированы в app.models и alembic/env.py.
- Создан скрипт scripts/write_dialysis_migration.py для записи миграции (alembic/versions в .cursorignore). Запуск: `python scripts/write_dialysis_migration.py`, затем `alembic upgrade head`.
- Реализована утилита is_dialysis_day в app/dialysis/service.py и экспорт из app.dialysis.
- Реализованы API: GET/POST /api/v1/centers; GET/POST /api/v1/patients/{id}/schedules; PUT /api/v1/schedules/{id}/close-and-replace; POST /api/v1/import/schedules и /import/schedules/confirm с in-memory IMPORT_PREVIEWS (TTL 10 мин, TODO: Redis).
- Добавлены страницы исследователя: /researcher/centers (центры), вкладка расписания в карточке пациента (модалы), /researcher/import/schedules (импорт CSV).
- Добавлены тесты в tests/dialysis/test_dialysis.py (is_dialysis_day с моком, 401 для API без авторизации). В test_migrations.py добавлены проверки таблиц centers и dialysis_schedules.

**Файлы:**
- app/dialysis/: __init__.py, models.py, schemas.py, crud.py, service.py, router.py, csv_import.py
- app/users/models.py (center_id), app/models/__init__.py, alembic/env.py, app/main.py, app/pages/router.py
- frontend/researcher/: centers.html, centers.js, import_schedules.html, import_schedules.js, schedule_import_template.csv; dashboard.html, js/patients.js, css/researcher.css
- tests/dialysis/test_dialysis.py, tests/test_migrations.py
- scripts/write_dialysis_migration.py

**Результат:** Модуль реализован. Миграцию нужно применить вручную (скрипт + alembic upgrade). Тесты запускать из venv: `python -m pytest tests/dialysis/ -v`.

**Проблемы:** Нет.
