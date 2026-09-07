# GPT Support

Платформа поддержки пациентов на программном гемодиализе. Это НЕ система лечения:
платформа обеспечивает психообразование, трекинг самоменеджмента, поддержку и
сбор данных для исследователя, медицинских решений не принимает.

В проекте объединены patient-facing web UI, панель исследователя, обучающие
модули, шкалы, витальные показатели, трекинг сна, рутина, медикаменты и
LLM-слой для диалоговой поддержки (реактивный чат + проактивные сообщения).

Этот `Readme.md` — каноническая сводка по текущему состоянию проекта.
Подробный статус агентского/LLM-контура по спринтам — в `ROADMAP_AGENT.md`
(корень) — это основной документ по нему, здесь только срез архитектуры.

## Стек

| Слой | Технологии |
| --- | --- |
| Backend | FastAPI (ASGI), uvicorn |
| БД | PostgreSQL, asyncpg, pgvector (RAG-эмбеддинги) |
| ORM | SQLAlchemy 2.0 async |
| Миграции | Alembic |
| Валидация | Pydantic v2 |
| Авторизация | Session-based, bcrypt (passlib) |
| Планировщик | APScheduler (проактивные сообщения) |
| LLM-провайдеры | GigaChat API (Сбер, OAuth) и Cloud.ru Evolution Foundation Models (OpenAI-совместимый шлюз) — переключаются флагом `LLM_PROVIDER`/кнопкой в admin-панели, без пересборки |
| Frontend | HTML5, Vanilla JS, CSS (без фреймворков) |
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

Если локальный debug-чат ходит в GigaChat через self-signed или корпоративный
сертификат и падает с `CERTIFICATE_VERIFY_FAILED`, для временного локального
обхода можно запустить сервер так:

```powershell
$env:GIGACHAT_ALLOW_INSECURE_SSL="true"; uvicorn app.main:app --reload
```

Важно: `GIGACHAT_ALLOW_INSECURE_SSL=true` отключает проверку TLS и подходит
только для локальной отладки. Для нормальной настройки используйте
`GIGACHAT_CERT_PATH`.

### Windows / UTF-8

Если PowerShell показывает кракозябры вместо русского текста:

```powershell
. .\scripts\dev_utf8.ps1
```

### Переменные окружения

Полный и актуальный список — в `.env.example` (с комментариями). Ключевые
блоки: `DATABASE_URL`; `SCHEDULER_ENABLED` (проактивный планировщик, off по
умолчанию); `LLM_SAFETY_LLM` (LLM-классификатор суицид-риска, on по
умолчанию); `LLM_PROVIDER` (`sber` default | `cloudru`); `GIGACHAT_KEY_<id>`
(один или несколько аккаунтов Сбера — N ключей = N параллельных потоков);
`CLOUD_RU_KEY`/`CLOUD_RU_MODEL*` (Cloud.ru); `CHAT_RATE_LIMIT_*`.

## Архитектура верхнего уровня

```text
Frontend (patient / researcher / doctor — статика)
        |
        v
    FastAPI API (app/main.py, роутеры по модулям)
        |
        +--> PostgreSQL (по схемам, см. ниже)
        |
        +--> LLMPipeline.process(LLMRequest) --> GigaChat (Сбер) / Cloud.ru
        |
        +--> APScheduler (проактивные сообщения, в lifespan за SCHEDULER_ENABLED)
```

Основные входные точки:

- `app/routers/chat.py` — `POST /api/chat/message`, история, mark-read, undo/confirm vitals.
- `app/researchers/router.py` — панель исследователя, debug-chat, переключатель LLM-провайдера.
- `app/llm/on_login.py` / `app/llm/proactive_coordinator.py` — проактивные сообщения при входе и по расписанию.
- `app/pages/router.py` — раздача HTML-страниц patient/researcher/doctor.

Во всех LLM-сценариях (реактивный чат, debug-chat, проактив) запросы идут в
единый `LLMPipeline.process(LLMRequest)`.

## Основные модули

- `app/auth/` — аутентификация пациентов и исследователей, session-based auth.
- `app/users/` — пользователи, онбординг, профильные данные.
- `app/consent/` — согласия на обработку персональных данных.
- `app/scales/` — HADS, KOP-25A, PSQI, PSS-10, WCQ, KDQOL-SF 1.3.
- `app/vitals/` — АД, пульс, вес, вода.
- `app/education/` — уроки, тесты, прогресс, импорт контента из markdown.
- `app/practices/` — самостоятельные практики и лог их выполнения.
- `app/medications/` — назначения препаратов и журнал приёмов.
- `app/routine/` — базовая рутина, дневные планы, вечерняя верификация (МКФ d230).
- `app/dialysis/` — центры и расписания диализа, CSV-импорт, soft-close.
- `app/sleep_tracker/` — трекинг сна (TIB/TST/SE), привязка к дням диализа.
- `app/profile/` — агрегированная сводка пациента, достижения.
- `app/notifications/` — бейджи сайдбара, достижения/бейджи, стрики.
- `app/researchers/` — панель исследователя: пациенты, центры, debug-инструменты.
- `app/rag/` — индексация и поиск по контенту уроков (эмбеддинги, pgvector).
- `app/llm/` — маршрутизация, безопасность, prompt-слой, pipeline, агент, память, проактив, трейс.
- `app/gpt_support/` — модуль-заглушка (не трогать без явной задачи).
- `app/core/` — конфиг (`config.py`), рантайм-настройки (`app_settings.py`, таблица `public.app_settings`).

## База данных

Проект использует PostgreSQL с разделением по схемам. Центральная сущность
пациента — `users.users`; почти все пользовательские показатели связаны с ней
через `patient_id` или `user_id` и удаляются каскадно при удалении пациента.

### Схемы и назначение

| Схема | Что хранит |
| --- | --- |
| `users` | Пациенты, исследователи, session-based авторизация и consent-флаги. |
| `vitals` | Ручные измерения давления, пульса, веса и объёма жидкости. |
| `scales` | Универсальные результаты психометрических шкал, кроме KDQOL. |
| `kdqol` | Точки измерения KDQOL-SF 1.3, ответы и рассчитанные субшкалы 0-100. |
| `sleep` | Ежедневные записи сна с расчётными TIB/TST/SE. |
| `routine` | Базовый шаблон рутины, дневные планы и вечерняя верификация. |
| `medications` | Назначения препаратов и фактические приёмы. |
| `education` | Уроки, карточки, тесты, прогресс и логи практик внутри уроков. |
| `practices` | Отдельные практики (каталог `pNNN`) и факты их выполнения. |
| `llm` | Чат, память агента, дедуп проактива и технические метрики LLM-запросов. |
| `public` | Общие таблицы: `centers`, `dialysis_schedules`, `app_settings`, `alembic_version`, бейджи/стрики. |

### Схема `llm` подробнее

| Таблица | Назначение |
| --- | --- |
| `llm.chat_messages` | Сообщения `user/assistant`, текст, `buttons_json`, `is_read`, `request_type`. |
| `llm.chat_supervisor_states` | Сериализованное состояние диалога агента (goal/slots/technique progress) по треду. |
| `llm.chat_summaries` | Rolling summary свёрнутых ходов диалога (episodic-память). |
| `llm.patient_facts` / `llm.patient_fact_history` | Устойчивая (semantic) память о пациенте с TTL и порогом подтверждений. |
| `llm.proactive_deliveries` | Дедуп-леджер отправленных проактивных сообщений (per patient/day/kind). |
| `llm.llm_request_logs` / `llm.llm_call_log` | Технические метрики вызовов: account_id, provider, tier, токены, latency, успех/ошибка. |

### Какие показатели собираем

| Домен | Таблицы | Показатели |
| --- | --- | --- |
| Профиль и доступ | `users.users`, `users.researchers`, `users.sessions` | ФИО, возраст, пол, диализный центр, внешние идентификаторы и контакты, номер пациента, PIN-hash, блокировка, onboarding, согласия на обработку данных, сессии входа. |
| Диализ | `public.centers`, `public.dialysis_schedules` | Центр, город, timezone, дни недели диализа, смена `morning/afternoon/evening`, период действия расписания, автор изменения и причина закрытия расписания. |
| Витальные | `vitals.bp_measurements`, `vitals.pulse_measurements`, `vitals.weight_measurements`, `vitals.water_intake` | АД: `systolic`, `diastolic`, опциональный `pulse`; пульс: `bpm`; вес: `weight`; жидкость: `volume_ml`, `liquid_type`. У всех записей есть `measured_at`, `session_id`, `context`, `created_at`, `updated_at`. |
| Шкалы | `scales.scale_results` | HADS, KOP-25A, PSQI, PSS-10, WCQ и другие шкалы: код шкалы, версия, дата измерения, сырые ответы `answers_json`, рассчитанный результат `result_json` с итоговыми баллами, субшкалами, уровнями и интерпретациями. |
| KDQOL-SF 1.3 | `kdqol.measurement_points`, `kdqol.kdqol_responses`, `kdqol.kdqol_subscale_scores` | Точки T0/T1/T2, активация исследователем, дата завершения, ответы по вопросам, рассчитанные субшкалы качества жизни в диапазоне 0-100. |
| Сон | `sleep.sleep_records` | Дата ночи, время засыпания и подъёма, TIB minutes, TST minutes, sleep efficiency %, число пробуждений, latency, утреннее самочувствие, дневной сон, нарушения сна, связь с днём диализа, поздний ввод, число правок. |
| Рутина | `routine.baseline_routines`, `routine.daily_plans`, `routine.daily_verifications` | Пул активностей, шаблоны диализного/недиализного дня, время планирования, дневной план, добавленные и кастомные активности, факт выполнения, незапланированные активности, `day_control_score`, ретроспективность и число правок. |
| Лекарства | `medications.medication_prescriptions`, `medications.medication_intakes` | Название препарата, доза и единица, кратность 1-6 раз в день, расписание приёма JSON, путь введения, даты начала/окончания, показание, инструкция, статус назначения, фактическое время приёма, фактическая доза, слот приёма, заметки, ретроспективный ввод. |
| Обучение | `education.lessons`, `education.lesson_cards`, `education.lesson_progress`, `education.lesson_tests`, `education.lesson_test_questions`, `education.lesson_test_results`, `education.practices`, `education.practice_logs` | Просмотр уроков, последняя карточка, завершение урока, выполнение встроенной практики, баллы тестов `score/max_score`, `passed`, ответы JSON, успешность практики, субъективный эффект 0-10 и комментарий. |
| Практики | `practices.practices`, `practices.practice_completions` | Каталог самостоятельных практик: модуль, тип, ICF-домен, контекст, инструкция JSONB, длительность. По пациенту хранится факт выполнения и `mood_after`. |
| LLM и чат | см. таблицу «Схема `llm` подробнее» выше | Сообщения диалога, состояние агента, память (semantic/episodic), дедуп проактива, технические метрики вызовов LLM (account/provider/tier, токены, latency, success/error). |
| Рантайм-настройки | `public.app_settings` | key/value-тумблеры админ-панели (сейчас — активный LLM-провайдер), кто и когда менял. |

### Как храним

- Измерения и события пишутся как отдельные append-like записи с временными
  полями (`measured_at`, `submitted_at`, `created_at`, `updated_at`). Для сна,
  рутины и расписаний есть уникальные ограничения на одну запись в день или
  один активный baseline/schedule.
- Структурированные числовые показатели хранятся отдельными колонками: АД,
  пульс, вес, объём жидкости, TIB/TST/SE, баллы KDQOL, дозировки, токены и
  latency.
- Гибкие ответы и вложенные формы хранятся в `JSON`/`JSONB`: ответы шкал,
  результаты шкал, расписание приёма лекарств, структуры планов и верификаций
  рутины, инструкции практик, кнопки чата.
- Временные ряды индексируются по пациенту и дате/времени, чтобы быстро
  собирать профиль пациента, исследовательские отчёты и контекст для LLM.
- Для историчности используются интервалы `valid_from`/`valid_to` в
  диализных расписаниях и baseline-рутине; старые версии не удаляются
  (soft-close, не delete).

## LLM-слой (`app/llm/`)

### Pipeline

Фиксированный runtime pipeline из пяти стадий (`app/llm/pipeline/pipeline.py`):

1. `boundary_guard` — режет prompt-injection; L0 (`router_l0.py`, regex,
   детерминированно) ловит кризис/острое медицинское состояние; второй
   эшелон суицид-риска — LLM-классификатор `safety_classifier.py` (рубрика
   `prompts/safety_classifier.txt`, флаг `LLM_SAFETY_LLM` default ON),
   градация `plan_or_imminent` (обрыв) / `ideation_active` (жёсткая плашка) /
   `ideation_passive` (мягкая плашка) / `distress` (concern-подсказка
   агенту).
2. `classification` — каскад L0 → L1 (kNN по эмбеддингам прототипов) → L2
   (Lite + json_schema) определяет `request_type`/`model_tier`/`domain_hint`.
3. `data_entry` — если L0 уверенно распознал числа (АД/пульс/вес/вода) или
   отчёт о сне/рутине, пишет их без обращения к модели и возвращает готовый
   `early_response` (с кнопкой в трекер для сна/рутины).
4. `supervisor` — один структурный вызов агента (`app/llm/agent/loop.py`,
   `Agent.run()`); модель возвращает плоскую карточку `AgentReply` (текст,
   `intent`, `safety_level`/`safety_kind`, `technique_id`,
   `memory_candidates`) одним вызовом вместо цепочки intake → delegation →
   expert; второй эшелон защиты (`_apply_agent_safety_net`) перекрывает ответ
   протоколом при `safety_level=urgent`, если ни L0, ни safety-классификатор
   это не подтвердили — гейт понижает до `concern` (де-эскалация
   перестраховки на гипотетических формулировках,
   `router_l0.looks_like_health_catastrophizing`).
5. `memory_write` — нормализует диагностику, сохраняет кандидатов из
   `AgentReply.memory_candidates` в устойчивую память пациента.

Любая стадия, выставившая `early_response`, завершает pipeline — дальше
ничего не выполняется. Подробное описание контрактов, промпт-слоёв и
кэширования — `app/llm/pipeline/STRUCTURE.md`.

### Два LLM-провайдера

`app/llm/pool.py` держит клиентов **обоих** провайдеров одновременно и
переключает активный без пересборки процесса:

- **Сбер GigaChat API** (OAuth, scope PERS) — прод по умолчанию. Один или
  несколько аккаунтов (`GIGACHAT_KEY_<id>`), каждый обслуживает все три тира
  (lite/pro/max), конкурентность = число ключей.
- **Cloud.ru Evolution Foundation Models** — OpenAI-совместимый шлюз,
  `CLOUD_RU_KEY` как Bearer-токен, флагман GigaChat 3.5 Ultra, выше
  конкурентность на ключ.

Переключение — флагом `LLM_PROVIDER` (env) или кнопкой в researcher-панели
(`public.app_settings`, применяется в рантайме через
`pool.set_active_provider()`, сохранённый выбор в БД имеет приоритет над env
при старте). Эмбеддинги (RAG, роутер L1) всегда идут через Сбер — индекс
построен на модели `Embeddings`.

### Проактивные сообщения

`app/llm/proactive_coordinator.py` — единая точка: собирает кандидатов
(аномалии, утренний дайджест, мотиватор, доменный нудж) у всех подсистем,
ранжирует по приоритету (кризис → аномалия → пропуски → простой/домен →
похвала), режет потолком в день и дедуплицирует через
`llm.proactive_deliveries`. Запускается двумя путями:

- **при входе пациента** (`app/llm/on_login.py`, `run_login_proactive`) —
  без генерации LLM (шаблонные тексты), доставка только в историю чата;
- **по расписанию** (`app/llm/scheduler.py`, APScheduler в lifespan за
  `SCHEDULER_ENABLED`, cron 08:00/14:00/20:00 МСК) — с генерацией через
  pipeline.

Отдельного канала доставки (push/Telegram) нет и не планируется — сообщение
ждёт пациента в истории чата, бейдж в сайдбаре поднимается при визите.

### Debug и трассировка

В панели исследователя есть debug-chat (свой thread `debug-*`) и экспорт
отчётов; переключатель LLM-провайдера — на дашборде и в debug-chat. В
`diagnostics` сохраняются карточка агента (`intent`, `safety_level`,
`technique_id`, ...), state delta, provider/model tier, account id, latency,
токены.

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

### Patient UI (`frontend/patient/`)

Основные сценарии: вход по patient number + PIN; онбординг; витальные
показатели; шкалы; обучение; практики; сон; рутина; медикаменты; профиль;
чат с ассистентом.

### Researcher UI (`frontend/researcher/`)

Основные сценарии: вход по логину/паролю; создание пациентов; сброс PIN;
управление центрами; импорт расписаний; debug-chat / chat monitor;
переключатель LLM-провайдера; метрики по модулям.

### Doctor UI (`frontend/doctor/`)

Дашборд для врача — в разработке, минимальный набор экранов.

## Дальнейшее развитие

Актуальный статус по фазам, спринтам и открытым задачам агентского контура —
`ROADMAP_AGENT.md` (корень репозитория). Развёрнутые отчёты по отдельным
расследованиям — `docs/agent/`.

## Полезные файлы

- [ROADMAP_AGENT.md](D:/PROJECT/GPT-SUPPORT/ROADMAP_AGENT.md)
- [app/llm/pipeline/STRUCTURE.md](D:/PROJECT/GPT-SUPPORT/app/llm/pipeline/STRUCTURE.md)
- [app/llm/pipeline/stages/supervisor.py](D:/PROJECT/GPT-SUPPORT/app/llm/pipeline/stages/supervisor.py)
- [app/llm/agent/loop.py](D:/PROJECT/GPT-SUPPORT/app/llm/agent/loop.py)
- [app/llm/agent/schemas.py](D:/PROJECT/GPT-SUPPORT/app/llm/agent/schemas.py)
- [app/llm/pool.py](D:/PROJECT/GPT-SUPPORT/app/llm/pool.py)
- [app/researchers/router.py](D:/PROJECT/GPT-SUPPORT/app/researchers/router.py)
