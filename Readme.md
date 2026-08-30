# GPT Support

Платформа поддержки пациентов на гемодиализе. В проекте объединены patient-facing web UI, панель исследователя, обучающие модули, шкалы, витальные показатели, трекинг сна, рутина, медикаменты и LLM-слой для диалоговой поддержки.

Этот `Readme.md` — каноническая сводка по текущему состоянию проекта. Содержимое из `UPD_Readme.md` слито сюда и приведено к актуальной архитектуре.

## Стек

| Слой | Технологии |
| --- | --- |
| Backend | FastAPI, uvicorn |
| БД | PostgreSQL, asyncpg |
| ORM | SQLAlchemy 2.0 async |
| Миграции | Alembic |
| Валидация | Pydantic v2 |
| Frontend | HTML, Vanilla JS, CSS |
| Тесты | pytest, pytest-asyncio |

## Быстрый старт

```bash
pip install -r requirements.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Тесты:

```bash
pytest
```

## Локальная разработка

### GigaChat SSL в dev

Если локальный debug-чат ходит в GigaChat через self-signed или корпоративный сертификат и падает с `CERTIFICATE_VERIFY_FAILED`, для временного локального обхода можно запустить сервер так:

```powershell
$env:GIGACHAT_ALLOW_INSECURE_SSL="true"; uvicorn app.main:app --reload
```

Важно: `GIGACHAT_ALLOW_INSECURE_SSL=true` отключает проверку TLS и подходит только для локальной отладки. Для нормальной настройки используйте `GIGACHAT_CERT_PATH`.

### Windows / UTF-8

Если PowerShell показывает кракозябры вместо русского текста:

```powershell
. .\scripts\dev_utf8.ps1
```

## Архитектура верхнего уровня

```text
Frontend (web)
        |
        v
    FastAPI API
        |
        v
    PostgreSQL
```

Основные входные точки:

- `app/routers/chat.py`
- `app/researchers/router.py`
- `app/llm/proactive_coordinator.py`
- `app/pages/router.py`

Во всех основных LLM-сценариях запросы идут в `LLMPipeline.process(LLMRequest)`.

## Основные модули

- `app/auth/` — аутентификация пациентов и исследователей, session-based auth.
- `app/users/` — пользователи, consent, профильные данные.
- `app/scales/` — HADS, KOP-25A, PSQI, PSS-10, WCQ, KDQOL-SF 1.3.
- `app/vitals/` — АД, пульс, вес, вода.
- `app/education/` — уроки, тесты, прогресс, lesson content import.
- `app/practices/` — самостоятельные практики и completion logs.
- `app/medications/` — назначения и журнал приемов.
- `app/routine/` — шаблон рутины, дневные планы, верификация.
- `app/dialysis/` — центры и расписания диализа, CSV import.
- `app/sleep_tracker/` — трекинг сна, TIB/TST/SE, привязка к дням диализа.
- `app/consent/` — согласия на обработку данных.
- `app/profile/` — агрегированная сводка пациента.
- `app/researchers/` — панель исследователя, patient management, debug tools.
- `app/llm/` — маршрутизация, prompt-слой, pipeline, supervisor, memory, trace.

## База данных

Проект использует PostgreSQL с разделением по схемам. Центральная сущность пациента — `users.users`; почти все пользовательские показатели связаны с ней через `patient_id` или `user_id` и удаляются каскадно при удалении пациента.

### Схемы и назначение

| Схема | Что хранит |
| --- | --- |
| `users` | Пациенты, исследователи, session-based авторизация и consent-флаги. |
| `vitals` | Ручные измерения давления, пульса, веса и объема жидкости. |
| `scales` | Универсальные результаты психометрических шкал, кроме KDQOL. |
| `kdqol` | Точки измерения KDQOL-SF 1.3, ответы и рассчитанные субшкалы 0-100. |
| `sleep` | Ежедневные записи сна с расчетными TIB/TST/SE. |
| `routine` | Базовый шаблон рутины, дневные планы и вечерняя верификация. |
| `medications` | Назначения препаратов и фактические приемы. |
| `education` | Уроки, карточки, тесты, прогресс и логи практик внутри уроков. |
| `practices` | Отдельные практики и факты их выполнения. |
| `llm` | История чата и технические метрики запросов к LLM. |
| `public` | Общие таблицы: `centers`, `dialysis_schedules`, `alembic_version`. |

### Какие показатели собираем

| Домен | Таблицы | Показатели |
| --- | --- | --- |
| Профиль и доступ | `users.users`, `users.researchers`, `users.sessions` | ФИО, возраст, пол, диализный центр, внешние идентификаторы и контакты, номер пациента, PIN-hash, блокировка, onboarding, согласия на обработку данных, сессии входа. |
| Диализ | `public.centers`, `public.dialysis_schedules` | Центр, город, timezone, дни недели диализа, смена `morning/afternoon/evening`, период действия расписания, автор изменения и причина закрытия расписания. |
| Витальные | `vitals.bp_measurements`, `vitals.pulse_measurements`, `vitals.weight_measurements`, `vitals.water_intake` | АД: `systolic`, `diastolic`, опциональный `pulse`; пульс: `bpm`; вес: `weight`; жидкость: `volume_ml`, `liquid_type`. У всех записей есть `measured_at`, `session_id`, `context`, `created_at`, `updated_at`. |
| Шкалы | `scales.scale_results` | HADS, KOP-25A, PSQI, PSS-10, WCQ и другие шкалы: код шкалы, версия, дата измерения, сырые ответы `answers_json`, рассчитанный результат `result_json` с итоговыми баллами, субшкалами, уровнями и интерпретациями. |
| KDQOL-SF 1.3 | `kdqol.measurement_points`, `kdqol.kdqol_responses`, `kdqol.kdqol_subscale_scores` | Точки T0/T1/T2, активация исследователем, дата завершения, ответы по вопросам, рассчитанные субшкалы качества жизни в диапазоне 0-100. |
| Сон | `sleep.sleep_records` | Дата ночи, время засыпания и подъема, TIB minutes, TST minutes, sleep efficiency %, число пробуждений, latency, утреннее самочувствие, дневной сон, нарушения сна, связь с днем диализа, поздний ввод, число правок. |
| Рутина | `routine.baseline_routines`, `routine.daily_plans`, `routine.daily_verifications` | Пул активностей, шаблоны диализного/недиализного дня, время планирования, дневной план, добавленные и кастомные активности, факт выполнения, незапланированные активности, `day_control_score`, ретроспективность и число правок. |
| Лекарства | `medications.medication_prescriptions`, `medications.medication_intakes` | Название препарата, доза и единица, кратность 1-6 раз в день, расписание приема JSON, путь введения, даты начала/окончания, показание, инструкция, статус назначения, фактическое время приема, фактическая доза, слот приема, заметки, ретроспективный ввод. |
| Обучение | `education.lessons`, `education.lesson_cards`, `education.lesson_progress`, `education.lesson_tests`, `education.lesson_test_questions`, `education.lesson_test_results`, `education.practices`, `education.practice_logs` | Просмотр уроков, последняя карточка, завершение урока, выполнение встроенной практики, баллы тестов `score/max_score`, `passed`, ответы JSON, успешность практики, субъективный эффект 0-10 и комментарий. |
| Практики | `practices.practices`, `practices.practice_completions` | Каталог самостоятельных практик: модуль, тип, ICF-домен, контекст, инструкция JSONB, длительность. По пациенту хранится факт выполнения и `mood_after`. |
| LLM и чат | `llm.chat_messages`, `llm.llm_request_logs` | Сообщения `user/assistant`, текст, использованные токены, модель, домен, тип запроса, а также технические метрики LLM: account ID, tier `lite/pro/max`, input/output tokens, latency, success/error. |

### Как храним

- Измерения и события пишутся как отдельные append-like записи с временными полями (`measured_at`, `submitted_at`, `created_at`, `updated_at`). Для сна, рутины и расписаний есть уникальные ограничения на одну запись в день или один активный baseline/schedule.
- Структурированные числовые показатели хранятся отдельными колонками: АД, пульс, вес, объем жидкости, TIB/TST/SE, баллы KDQOL, дозировки, токены и latency.
- Гибкие ответы и вложенные формы хранятся в `JSON`/`JSONB`: ответы шкал, результаты шкал, расписание приема лекарств, структуры планов и верификаций рутины, инструкции практик.
- Временные ряды индексируются по пациенту и дате/времени, чтобы быстро собирать профиль пациента, исследовательские отчеты и контекст для LLM.
- Для историчности используются интервалы `valid_from`/`valid_to` в диализных расписаниях и baseline-рутине; старые версии не удаляются.

## Текущее состояние LLM-слоя

### Pipeline

Фиксированный runtime pipeline:

1. `boundary_guard`
2. `classification`
3. `supervisor`
4. `memory_write`

`LLMRequest` сейчас содержит только runtime-поля:

- `patient_id`
- `user_input`
- `source`
- `supervisor_state`
- `router_result`
- `strict_model_tier`
- `db`

### Supervisor: одноагентная ветка

`supervisor` делает один структурный LLM-вызов (`app/llm/agent/loop.py`,
`Agent.run()`) вместо цепочки intake → delegation → expert. Модель возвращает
плоскую карточку `AgentReply` (`app/llm/agent/schemas.py`) одним вызовом:

- текст ответа пациенту;
- `intent` (`emotional_support` / `education` / `smalltalk` / `safety`);
- `safety_level` / `safety_kind` — второй эшелон защиты
  (`_apply_agent_safety_net`) перекрывает ответ протоколом при `urgent`;
- `technique_id` — прогресс по интерактивной технике;
- `memory_candidates` — кандидаты в устойчивую память пациента.

Ранее рядом с этой веткой под флагом `LLM_SINGLE_AGENT` жила старая ветка
Graph v2 (`intake_analyze → ... → finalize_reply`,
`app/llm/langgraph_supervisor/`) — она удалена вместе с флагом, одноагентная
ветка теперь единственная.

### Debug и трассировка

В панели исследователя есть debug-chat и экспорт отчетов, а в `diagnostics` сохраняются:

- graph path (`["agent"]`);
- карточка агента (`intent`, `safety_level`, `technique_id`, ...);
- state delta;
- model tier, account ids, latency, tokens.

## Эксперты: текущая и целевая линия

### Что есть сейчас

Реальным runtime-экспертом сейчас является одноагентная ветка `supervisor`
(см. выше) — эмоциональная поддержка и лёгкое образование внутри одной
карточки `AgentReply`.

### Ближайший фокус

Сначала стабилизируем экспертный слой, а уже потом строим `related_domain_scorer`.

Причина:

- `intake` специально ограничен одной главной жалобой и одним контекстом;
- если расширять `intake` до нескольких намерений, диалог станет длиннее и хрупче;
- если заставить `emotional_support` самому искать все вторичные причины, он перегрузится оркестрацией.

### Текущий продуктовый вектор

Целевая линия развития LLM:

1. `intake` фиксирует главную жалобу.
2. `delegation` передает ее в основной экспертный слой.
3. `emotional_support` дает поддержку и стабилизацию.
4. После стабилизации система может предлагать следующий полезный вектор помощи.

Но это должно строиться поэтапно:

- сначала проектируем и стабилизируем набор экспертов и их роли;
- потом добавляем `related_domain_scorer`, который не разговаривает с пользователем напрямую, а только оценивает возможные следующие домены/векторы;
- затем отдельно решаем UX показа next-step suggestions.

### Про `related_domain_scorer`

Это не часть текущего graph runtime. Это следующая ступень после стабилизации экспертного слоя.

Его предполагаемая роль:

- не вести диалог;
- не ломать принцип `1 проблема -> 1 контекст` в intake;
- оценивать связанные направления на основе уже известных данных:
  - главной жалобы;
  - минимального `intake_context`;
  - patient summary;
  - sleep / meds / routine / scales;
  - history / signals / domain scores.

Задача `related_domain_scorer` — не “лечить все сразу”, а помогать выбрать следующий лучший вектор после базовой поддержки.

## Импорт контента

```bash
# psychology lessons
python scripts/import_lesson_from_md.py --block psychology --dir content/education/psychology

# psychology tests
python scripts/import_lesson_test_from_json.py --block psychology --dir content/education/psychology

# nephrology lessons
python scripts/import_lesson_from_md.py --block nephrology --dir content/education/nephrology

# nephrology tests
python scripts/import_lesson_test_from_json.py --block nephrology --dir content/education/nephrology

# standalone practices
python scripts/import_practices.py
```

## Исследовательский и patient UI

### Patient UI

Основные сценарии:

- вход по patient number + PIN;
- онбординг;
- витальные показатели;
- шкалы;
- обучение;
- практики;
- сон;
- рутина;
- медикаменты;
- профиль.

### Researcher UI

Основные сценарии:

- вход по логину/паролю;
- создание пациентов;
- сброс PIN;
- управление центрами;
- импорт расписаний;
- debug-chat / debug-report;
- метрики по модулям.

## Дорожная карта

Актуальный порядок приоритетов:

1. стабилизация expert-layer в LLM;
2. проектирование и реализация `related_domain_scorer`;
3. UX для следующего шага после emotional support;
4. дальнейшее развитие RAG / grounding / education hooks;
5. расширение proactive и memory-сценариев;
6. развитие doctor-facing monitoring.

## Полезные файлы

- [app/llm/pipeline/STRUCTURE.md](D:/PROJECT/GPT-SUPPORT/app/llm/pipeline/STRUCTURE.md)
- [app/llm/pipeline/stages/supervisor.py](D:/PROJECT/GPT-SUPPORT/app/llm/pipeline/stages/supervisor.py)
- [app/llm/agent/loop.py](D:/PROJECT/GPT-SUPPORT/app/llm/agent/loop.py)
- [app/llm/agent/schemas.py](D:/PROJECT/GPT-SUPPORT/app/llm/agent/schemas.py)
- [app/researchers/router.py](D:/PROJECT/GPT-SUPPORT/app/researchers/router.py)
