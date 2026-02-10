**Задача:** sleep_date, экран выбора ночи, проверка дубликата, редактирование записи.

**Дата:** 2026-02-10

**Действия:**
- Миграция 20260210_03: добавлены поля sleep_date (DATE NOT NULL), updated_at (TIMESTAMPTZ), retrospective_days (INT), edit_count (INT default 0), UNIQUE(patient_id, sleep_date), индекс по sleep_date. Для существующих строк: sleep_date = submitted_at::date - 1, updated_at = submitted_at, retrospective_days = 1.
- Модель SleepRecord: sleep_date, updated_at, retrospective_days, edit_count, UniqueConstraint(patient_id, sleep_date).
- Схемы: SleepRecordCreate — поле sleep_date (дата ночи с фронта); SleepRecordRead — sleep_date, updated_at, retrospective_days, edit_count; добавлена SleepRecordUpdate для PUT (без sleep_date).
- Сервис: prepare_record считает retrospective_days = (submitted_at.date - sleep_date).days; добавлен prepare_update для обновления.
- CRUD: get_by_patient_and_date(patient_id, sleep_date); update_record(record_id, patient_id, update_data) с updated_at = now(), edit_count += 1.
- API: GET /me/by-date?date=YYYY-MM-DD — запись за ночь (404 если нет); POST /me — в теле sleep_date; PUT /me/{record_id} — обновление, инкремент edit_count.
- Фронт: экран выбора ночи (4 ночи: текущая + 3 предыдущих, формат «Вт, 11 марта»), по [Продолжить] проверка GET by-date; при отсутствии записи — пустая форма; при наличии — диалог «Изменить запись?» [Изменить] [Отмена]; редактирование — форма с предзаполнением, кнопка «Сохранить изменения», PUT вместо POST.

**Файлы:**
- alembic/versions/20260210_03_sleep_date_and_meta.py
- app/sleep_tracker/models.py, schemas.py, service.py, crud.py, router.py
- frontend/patient/sleep_tracker.html, css/sleep_tracker.css, js/sleep_tracker.js

**Результат:** Одна запись на пациента и ночь (sleep_date). Выбор ночи → проверка дубликата → новая запись или редактирование с увеличением edit_count и обновлением updated_at.

**Проблемы:** Нет.
