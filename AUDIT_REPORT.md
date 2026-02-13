# Medications Module Audit

Дата аудита: 2026-02-12
Сравнение текущей реализации (Cursor AI) с ТЗ «Модуль Препараты».

## Backend issues

- [ ] **Модель данных не соответствует ТЗ**: UUID PK вместо Integer PK; dose хранится как String вместо Float + dose_unit; frequency_type (daily/specific_days) вместо frequency_times_per_day (1–6); times_of_day (массив Time) вместо intake_schedule (JSON слоты morning/afternoon/evening)
- [ ] **Нет поля prescribed_by**: отсутствует концепция врачебного назначения vs самоназначения
- [ ] **Нет adherence_rate**: не вычисляется ни на лету, ни в ответе API
- [ ] **Нет HTTP 403**: при попытке изменить/удалить врачебное назначение
- [ ] **Нет каскадного удаления intakes**: при DELETE prescription (ORM cascade есть, но модель другая)
- [ ] **Нет валидации end_date >= start_date**: в схемах Pydantic
- [ ] **Intake модель не совпадает**: scheduled_date + scheduled_time + status (taken/skipped) вместо intake_datetime + actual_dose + is_retrospective
- [ ] **Нет intake-валидаций**: не проверяется что intake_datetime не в будущем, не старше 24ч, нет проверки дубликатов (<5 мин → 409)
- [ ] **API paths не совпадают**: текущий `/api/v1/medications/`, ТЗ требует `/api/patient/medications/prescriptions` и `/intakes`
- [ ] **Нет полей**: indication, instructions, intake_slot, actual_dose, is_retrospective, route (в текущей модели)
- [ ] **Лишние сущности**: MedicationReference (справочник 54 препарата), MedicationHistory (audit trail), UserMedicationSettings — отсутствуют в ТЗ

## Frontend issues

- [ ] **Нет модального окна подтверждения** (#modalConfirm) — используется стандартный confirm
- [ ] **Нет модального окна редактирования препарата**: одна форма для add/edit с data-mode не реализована
- [ ] **Нет Frequency Picker**: кнопки 1–6 для выбора частоты приёма отсутствуют
- [ ] **Нет Schedule Picker**: выбор слотов morning/afternoon/evening отсутствует
- [ ] **Нет adherence badges**: на карточках назначений нет отображения % соблюдения
- [ ] **Нет slot tags**: на карточках не отображаются слоты расписания (☀ Утро, ☁ День, 🌙 Вечер)
- [ ] **API paths в fetch не совпадают**: JS обращается к `/api/v1/medications/`, ТЗ требует `/api/patient/medications/`
- [ ] **Формат дат**: не dd-mm-yy как требует ТЗ
- [ ] **Формат времени**: не гарантирован 24-часовой HH:MM
- [ ] **Нет предупреждения о врачебных назначениях**: отсутствует блокировка полей и предупреждение

## Missing functionality

- [ ] adherence_rate вычисление (expected vs actual за 30 дней)
- [ ] Разделение prescriptions / intakes как отдельных ресурсов API
- [ ] Врачебные назначения (prescribed_by) с защитой 403
- [ ] is_retrospective автоматическое определение (>30 мин от текущего времени)
- [ ] Конфликт 409 при дублировании приёма (<5 мин)
- [ ] Frequency picker UI (кнопки 1–6)
- [ ] Schedule picker UI (morning/afternoon/evening слоты с логикой выбора)
- [ ] 5 модальных окон с полным функционалом
- [ ] Предупреждение при дозе >50% от назначенной
- [ ] Responsive дизайн для мобильных (bottom sheet модалы)
