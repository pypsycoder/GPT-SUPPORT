 ROADMAP_AGENT.md — Дорожная карта агента поддержки

> **Статус на 2026-09-03**: всё накопленное **закоммичено и запушено** на
> `feat/agents-rework` (`8c14fdd..e035ef9`). Спринт 1 закрыт по коду, **Фаза 2
> закрыта по коду** (единый координатор + cutover), **Фаза 4 закрыта по коду**
> (`education_cta`, рейт-лимит, сон/routine из чата → кнопка, `proactive_anomaly.txt`,
> STRUCTURE.md, `buttons_json`, часовые пояса, миграция `account_id` применена).
> `crisis_semantic` — валидация провалена, слой удалён; L0 regex усилен + заведён
> LLM-классификатор суицид-риска (`safety_classifier.py`, флаг `LLM_SAFETY_LLM` ON):
> golden **test-сплит** (holdout) recall {act,plan}/self **91%**, FPR distress 3%,
> patient-sim 0 ложных кризис-эскалаций.
> **Фаза 3 (внешний канал доставки) снята** — доставка только веб.
> **Новое 2026-09-02:** решение — **два LLM-провайдера в коде, переключение флагом
> `LLM_PROVIDER` + кнопка в админ-панели**. Целевой прод — **Cloud.ru**
> (GigaChat 3.5 Ultra, больше одновременных запросов); Сбер PERS — резерв +
> источник для тестов (Freemium-токены, есть и GigaChat 3 Ultra через новый
> endpoint `api.giga.chat`). На safety-бенче (holdout, продовая рубрика)
> 3.5 Ultra: recall {act,plan} **0.97** против 0.86 у GigaChat-2-Pro и 0.78 у
> текущего прода (2-Lite), FPR 0.00. → Фаза 6. *(Код влит с дефолтом
> `LLM_PROVIDER=sber` — на мерже поведение не меняется; перевод на Cloud.ru —
> отдельным решением, флагом/кнопкой.)*
> **Фаза 6 (2026-09-03): код готов** — оба провайдера в пуле, переключатель
> `LLM_PROVIDER` + кнопка в researcher-панели (`app_settings`, миграция
> `20260903_01` применена), safety-классификатор и реактивный агент (structured +
> tool-calling + префиксный кэш 99.7 %) работают на Cloud.ru, 552 теста зелёные.
> **Дефолт — `sber`, прод НЕ переключён.** Health-anxiety на ходах 1–2 закрыт
> де-эскалацией (`89f2496` + L0-гард `e035ef9`): полный patient-sim на Cloud.ru —
> 24 PASS / 1 WARN / 4 FAIL, остатки не блокеры. Цена посчитана
> (`docs/agent/CLOUDRU_COST_ESTIMATE.md`). Хвост: Сбер на `api.giga.chat`
> (заблокировано с dev), решение о прод-cutover.
> **Открыто:** staging-smoke Фаз 1–2 → снести старые `deliver_*`; снять флаг
> `LLM_SAFETY_LLM`; Фаза 6 хвост (Сбер-endpoint, прод-cutover); Фаза 5 (нужна
> постановка исследователя).
> Детали — по фазам ниже (✅ готово · 🟡 код готов, ждёт staging · ⬜ не начато).

## Оглавление

- [Связанные документы](#связанные-документы)
- [Контекст](#контекст)
- [Зафиксированные решения (2026-08-28)](#зафиксированные-решения-2026-08-28)
- [Дорожная карта](#дорожная-карта)
  - [Фаза 0 — Проверить почву](#фаза-0--проверить-почву)
  - [Фаза 1 — Проактив доходит до пациента при входе](#фаза-1--проактив-доходит-до-пациента-при-входе)
  - [Фаза 2 — Проактив связный и тёплый](#фаза-2--проактив-связный-и-тёплый)
  - [Фаза 3 — ~~внешний канал доставки~~ снята](#фаза-3--внешний-канал-доставки-снята)
  - [Фаза 4 — Реактивные пробелы и гигиена](#фаза-4--реактивные-пробелы-и-гигиена)
  - [Фаза 5 — Инструментирование под исследование](#фаза-5--инструментирование-под-исследование)
  - [Фаза 6 — LLM-провайдер: два источника (Cloud.ru + Сбер)](#фаза-6--llm-провайдер-два-источника-cloudru--сбер-переключение-флагом)
  - [Сквозное — тесты](#сквозное--тесты)
- [Спринт 1 — «Проактив запускается и доходит до пациента при входе»](#спринт-1--проактив-запускается-и-доходит-до-пациента-при-входе)
- [Спринт 2 — предварительно](#спринт-2--предварительно)
- [Спринт 3 — предварительно](#спринт-3--предварительно)
- [Приложение — связь с находками аудита](#приложение--связь-с-находками-аудита)

## Связанные документы

Основной статус — здесь. Развёрнутые отчёты — в `docs/agent/` (политика: корневые
`.md` не плодить, см. `CLAUDE.md` → «Документация»):

| Документ | О чём |
|---|---|
| `SPRINT1_INVESTIGATIONS.md` (корень) | Аудит GigaChat-аккаунта (Фаза 0 §1), замер префиксного кэша (§2), Cloud.ru — ёмкость и решение о переходе (§1 доп. 2026-09-02) |
| `d:/PROJECT/safety-bench` (отд. репо) | Оффлайн-бенч детектора суицид-риска. §GigaChat 3.5 Ultra vs 2-Pro (2026-09-02): армы `giga35_prod` / `lite_pro_prod` / `lite_prod`, клиент `sbench/cloudru.py` |
| `docs/agent/CLOUDRU_COST_ESTIMATE.md` | Прикидка стоимости Cloud.ru / GigaChat 3.5 Ultra под перевод прода (Фаза 6) |
| `docs/agent/SAFETY_LLM_INTEGRATION_PLAN.md` | LLM-классификатор суицид-риска: контракт, встраивание, градация уровней, цифры |
| `docs/agent/CRISIS_SEMANTIC_VALIDATION.md` | Почему embedding-слой `crisis_semantic` провалил валидацию и удалён |
| `docs/agent/PLAN_TOMORROW.md` | План на 2026-09-01 + NIGHT REPORT (holdout-сверка safety, латентность, 2-й проход L0) |
| `docs/agent/MIGRATION_1NN_REPORT.md` | Миграция контента к схеме id 1NN/2NN/3NN — разведка, решения, `20260830_01` |
| `docs/agent/TASK_migration_content_ids.md` | Исходная постановка задачи по миграции id |
| `ALEMBIC_RUNBOOK.md` (корень) | Порядок запуска миграций, верификация revision, правила `stamp` |

## Контекст

Составлено по аудиту от 2026-08-28 (ветка `feat/agents-rework`, HEAD `2316a40`;
артефакт «Аудит агента поддержки»). Рамка «проактивный / реактивный контур» — из
постановки задачи. Ниже — исходная картина аудита; текущее состояние см. в
баннере выше и по галочкам.

Кратко из аудита:

- **Реактивный контур** работает в проде: `POST /api/chat/message` → 5 стадий
  (`boundary_guard → classification → data_entry → supervisor → memory_write`) →
  одноагентный структурный вызов.
- **Проактивный контур** написан целиком (`morning_service`, `proactive`,
  `motivator`), но **не запущен**: `start_scheduler()` вызывается только из
  отдельного процесса `python -m app.llm.worker` при `SCHEDULER_ENABLED=true`;
  флага нет в `.env`, в lifespan приложения планировщик не стартует.
- **Триггера «при первом входе» не существует.** Заготовка
  `ensure_morning_message()` (идемпотентная, с advisory-lock) написана и никуда
  не подключена.
- **Доставка проактива — только веб.** Сообщение падает в `llm.chat_messages` и
  всплывает при следующем визите пациента (сайдбар грузит бейджи один раз на
  `DOMContentLoaded`, чат — историю один раз при открытии). Это и есть принятая
  модель: отдельный канал напоминаний не планируется.
- Две сквозные фичи оборваны на интеграции: `/api/chat/mark-read` — фронт зовёт,
  эндпоинта нет (404), бейдж «ассистент» не сбрасывается; `education_cta` —
  захардкожен `None` в супервизоре.
- ~~Пул GigaChat: единственный персональный ключ, конкурентность = 1.~~
  **Снято 2026-09-02:** добавлен 2-й ключ `GIGACHAT_KEY_L1` (аккаунт Лены).
  `AccountPool` обобщён: каждый `GIGACHAT_KEY_<id>` = аккаунт со своим локом,
  все три тира на аккаунт (`<id>-lite/-pro/-max`). Конкурентность = число
  ключей (сейчас 2). Оба ключа проверены на lite/pro/max. `scheduler`
  `_PROACTIVE_CONCURRENCY` = `pool.account_count`. См. `SPRINT1_INVESTIGATIONS.md`
  §1 (дополнение 2026-09-02).

## Зафиксированные решения (2026-08-28)

| Вопрос | Решение | Следствие для плана |
|---|---|---|
| Топология деплоя | Один инстанс uvicorn | Планировщик — в lifespan `app/main.py` за флагом; advisory-lock из `worker.py` переносится туда же (защита от `--workers N`) |
| Ёмкость спринта 1 | Один разработчик, 1 неделя | Спринт 1 урезан до investigation + `mark-read` + триггер входа |
| Канал доставки *(2026-08-30)* | **Только веб.** Сообщение ждёт в истории чата, бейдж поднимается при визите | Внешний канал (Telegram/push) — мёртвая идея, из плана убран. Фаза 3 снята |
| Порядок после спринта 1 | Сначала довести проактив (Фаза 2), затем реактивная гигиена (Фаза 4) | Фазы идут последовательно, один разработчик |
| Ключ GigaChat *(2026-08-29 → пересмотрено 2026-09-02)* | ~~Один ключ~~ → **2 ключа** (`GIGACHAT_KEY_A1` Дима, `GIGACHAT_KEY_L1` Лена), оба без ограничений | Конкурентность = число ключей (2). `AccountPool` обобщён под N ключей; будущие ключи подхватываются автоматически. Проактив: `_PROACTIVE_CONCURRENCY = pool.account_count`. Для «десятков разом» всё равно нужен аккаунт юрлица. См. `SPRINT1_INVESTIGATIONS.md` §1 |
| LLM-провайдер *(2026-09-02; код 2026-09-03)* | **Два провайдера в коде, переключение флагом `LLM_PROVIDER` (`cloudru`\|`sber`, default `sber`) + кнопка в researcher-панели.** Целевой прод: Cloud.ru / GigaChat 3.5 Ultra (`ai-sage/GigaChat3.5-432B-A28B`). Тесты/резерв: Сбер PERS (Freemium; GigaChat 3 Ultra через `api.giga.chat`) | Cloud.ru — больше одновременных (~16/ключ). Сбер — бесплатные Freemium-токены, потоки для оффлайн-батча не важны. **Код готов (`1729e7d`..`e035ef9`):** Cloud.ru-клиент в `app/llm/pool.py`, `public.app_settings` + миграция `20260903_01` (применена), переключатель в researcher-панели. Хвост: перевод Сбера на `api.giga.chat`, прод-cutover. См. Фаза 6 |

## Дорожная карта

Порядок задан зависимостями: сначала убедиться, на чём агент реально работает;
потом включить проактив для сценария «вход пациента» (сообщение ждёт в истории
чата — отдельный канал доставки не нужен и не планируется); потом сделать
проактив связным; потом реактивная гигиена.

### Фаза 0 — Проверить почву

**Цель:** снять неопределённость, которая иначе обесценит остальную работу.

- [x] **Аудит GigaChat-аккаунта.** → отчёт `SPRINT1_INVESTIGATIONS.md` §1.
  Ключ обслуживает lite/pro/max (свежая проверка + 9.5к историч. `ok`-вызовов,
  0 отказов авторизации). Лимит одновременных = 1 на ключ + низкий RPM;
  429 приходят только в batch-прогонах. **Обновление 2026-09-02: добавлен
  2-й ключ** `GIGACHAT_KEY_L1`, `AccountPool` обобщён под N ключей,
  конкурентность = 2 (см. Фаза 2, «Ограничение нагрузки»).
- [x] **Замер префиксного кэша.** → отчёт `SPRINT1_INVESTIGATIONS.md` §2.
  Тёплый ход (rn≥2): **cache_hit 80 %** (`agent` Pro — 88 %). Префикс стабилен —
  «дышащих» `prefix_fp` нет, нестабильных фрагментов в слоях 0–2 нет.
  *(2026-08-30 — `summarizer` не слал `X-Session-ID` (кэш мимо); добавлен общий
  `session_id="summarizer-shared"`, приём из `judge`.)*

**Оценка:** ~1 день. **Входит в спринт 1.** — сделано.

### Фаза 1 — Проактив доходит до пациента при входе

**Закрывает спеку:** п.4 (триггер) полностью; п.1–3 в минимальном виде.

- [x] Активировать планировщик в lifespan `app/main.py` за `SCHEDULER_ENABLED`;
  advisory-lock из `worker.py` перенести туда же; `SCHEDULER_ENABLED` и
  `LLM_CRISIS_SEMANTIC` — в `.env.example` с комментариями.
  *(2026-08-29 — lock-хелперы → `app/llm/scheduler.py` (общие с `worker.py`);
  lifespan берёт lock → `start_scheduler()`, на shutdown снимает; `worker.py`
  ужат до запасного пути; `.env.example` создан. Локальный smoke прошёл;
  multi-instance smoke на staging — при закрытии спринта.)*
- [x] Триггер `ensure_morning_message(patient_id)` из `patient_login` через
  `BackgroundTasks` + ленивый вызов из `GET /api/chat/history` при первом за
  день открытии. Функция уже идемпотентна (advisory-lock +
  `_is_morning_sent_today` + отсечка `now.hour < 6`). Cron оставить страховкой
  для тех, кто не заходил.
  *(2026-08-29 — `ensure_morning_message_bg()` (своя сессия, не пробрасывает) в
  `morning_service.py`; оба хука гейтятся на `is_onboarded && consent_personal_data`.
  Юнит-тесты + живая проверка идемпотентности на dev-Postgres. E2E на staging —
  при закрытии спринта.)*
- [x] `motivator` — ленивый вызов при входе. *(2026-08-29 —
  `deliver_motivator_messages_bg()`; единая точка `app/llm/on_login.py`
  `run_login_proactive()` = утро + мотиватор, вызывается из `patient_login` и
  `GET /api/chat/history`. Оба хода шаблонные, без LLM. Тесты:
  `test_on_login.py`, `test_login_proactive_trigger.py`.)*
- [ ] `proactive` — **сознательно НЕ на ленивый вызов.** Это LLM-путь (очередь
  по аномалиям/доменам, вызов пайплайна на каждое сообщение), а ключ GigaChat
  один и упирается в лимит (investigation #1). Остаётся на планировщике до
  единого координатора Фазы 2 + «Ограничения нагрузки».
- [x] Починить `mark-read`: `POST /api/chat/mark-read`
  (`UPDATE llm.chat_messages SET is_read = TRUE WHERE patient_id = :id AND
  role = 'assistant'`, commit в роутере). `proactive.py` привести к
  `is_read=False` — чтобы бейдж поднимался консистентно для всех трёх типов
  проактива. *(2026-08-29 — эндпоинт + `proactive.py` + `tests_py/routers/test_chat_mark_read.py`)*

**Итог:** пациент входит → видит утренний дайджест (аналитика за период +
невыполненные задачи + CTA «чем займёмся»); бейдж сбрасывается при прочтении.

**Оценка:** ~1 спринт. Часть (`mark-read`, триггер) — в спринте 1.

### Фаза 2 — Проактив связный и тёплый

**Закрывает спеку:** доводит п.1–3.

- [x] **Единый координатор** (`app/llm/proactive_coordinator.py`) — **cutover
  сделан 2026-08-30:**
  - `ProactiveCandidate` (kind / dedup_key / domain / text|llm_prompt);
  - `collect_candidates()` — адаптеры к `anomaly`, `morning_service`,
    `motivator`, **`domain_scorer`** (доменный нудж < 0.5); при холодном старте
    (`has_tracked_data == False`) `idle` и `domain` не собираются;
  - `select_candidates()` — чистая: приоритет (кризис 0 → аномалия 1 →
    пропуски 2 → простой/домен 3 → похвала 4), потолок `DEFAULT_DAILY_CAP = 2`
    (кризис сверх потолка), «один повод на домен», дроп уже отправленных
    ключей, `allow_llm=False` — отбрасывает поводы, требующие генерации;
  - кризисная аномалия — **шаблон** (`_crisis_anomaly_text`), доходит и на
    login; WARNING/доменные — LLM (`_render_via_pipeline`);
  - `deliver_selected()` — commit **после каждого повода** (сбой одного не
    теряет остальные и не оставляет сессию в rollback); morning-повод пишет
    и `patient_daily_context` (его читает `get_daily_context_for_llm`);
  - дедуп: таблица `llm.proactive_deliveries` (миграция `20260829_01`,
    применена) + мосты `_is_morning_sent_today` / `_was_motivator_sent_today`;
  - **`scheduler`**: 5 cron-джоб → 3 (`cron_morning/afternoon/evening`), все
    зовут `run_proactive_coordination`, семафор = 1 + джиттер;
  - **`on_login.run_login_proactive`** → `run_proactive_coordination(trigger="login")`,
    `allow_llm=False` (генерацию в момент входа не запускаем);
  - старые `deliver_morning_message` / `deliver_proactive_messages` /
    `deliver_motivator_messages` / `*_bg` **пока не удалены** — снести после
    smoke на staging;
  - тесты: `test_proactive_coordinator.py` (12), обновлены `test_on_login.py`,
    `test_proactive.py`. Проверено на dev-БД (login: morning+motivator, cron:
    +доменный нудж; повторный вход — no-op).
- [x] **Позитивная аналитика недели** *(2026-08-29)*. `morning_service`:
  `build_daily_context` считает `recent_lessons_completed` /
  `recent_practices_completed` за 7 дней (плюс уже были sleep/med-days,
  streak); `_build_achievement_lines()` → ≤2 фразы достижений,
  `_build_weekly_summary` собирает `achievement_summary` («На этой неделе вы
  прошли 2 занятия и почти каждый день отмечали сон — здорово»);
  `build_morning_message` ставит её **перед** проблемными строками;
  `get_daily_context_for_llm` отдаёт «за неделю: …» реактивному агенту.
  Серия по лекарствам — только если у дайджеста не будет своего блока про неё.
  Тесты: `test_morning_service.py` (+6). Проверено на dev-БД.
- [x] **Подключить `get_daily_context_for_llm`** *(2026-08-30)*. `SupervisorStage`
  → `_run_single_agent` тянет строку и кладёт её в волатильный слой агента
  (`build_agent_user_prompt` → `daily_context`, перед `l0_note`). Не в
  стабильные слои — `prefix_fingerprint` не меняется (тест). Дата чтения
  сведена к МСК (как при записи). Диагностика: `prompt_layers.daily_context_used`.
- [x] **Холодный старт** *(2026-08-30)*. `domain_scorer.has_tracked_data()` —
  есть ли у пациента хоть какие-то данные (АД / приёмы / активные назначения /
  сон / практики / завершённые уроки). `morning_service`: при пустой БД дайджест
  = короткое знакомство (`_COLD_START_TEXT`), без «вчера не отмечено» и разбора
  недели. `proactive.generate_daily_queue` и `coordinator.collect_candidates`
  не добавляют доменные/idle-поводы. Кризис/аномалии от гейта не зависят.
- [x] **Ограничение нагрузки на GigaChat** *(2026-08-30)*. `scheduler`:
  `_PROACTIVE_CONCURRENCY = 1` + джиттер 0.5–1.5 с между пациентами (было
  `_CONCURRENCY = 5`). `http.py`: `429` → экспоненциальный backoff
  (2→4→8 с, потолок 8 с, уважает `Retry-After`), retries для `chat` 1 → 2.
  Утро/день/вечер разнесены на 08:00 / 14:00 / 20:00, cron-страховки нет —
  вход обслуживает координатор напрямую.

**Оценка:** 1–2 спринта. — Фаза 2 закрыта по коду 2026-08-30, ждёт staging-smoke.

### Фаза 3 — ~~внешний канал доставки~~ снята

Доставка — **только веб**: проактивное сообщение ждёт пациента в истории чата,
бейдж в сайдбаре поднимается при следующем визите. Внешний канал напоминаний
(Telegram/push) из плана убран 2026-08-30 — мёртвая идея.

Если позже понадобится «доставать» пациента вне визита — это отдельный эпик с
нуля (в репозитории кода бота нет), не часть этой дорожной карты.

### Фаза 4 — Реактивные пробелы и гигиена

- [x] **Сон из чата — минимум (спринт 1, #6).** SLEEP убран из
  `router_l0.parse_vitals` + `data_entry` — нет ложного «Записал: сон 3 ч».
- [x] **Сон из чата — кнопка в трекер** *(2026-08-30)*. L0 распознаёт отчёт о
  длительности сна (`_SLEEP_ENTRY_RE`, intent `sleep_entry`; жалоба рядом
  `_SLEEP_DISTRESS_RE` / эмоция / вопрос → мимо, к модели). `DataEntryStage`
  отвечает короткой репликой + кнопкой `«Внести данные о сне» → open_sleep`
  (`/patient/sleep_tracker`), без LLM. Кнопки раннего ответа проведены через
  `PipelineContext.early_response_buttons` → `LLMResponse.buttons` →
  `MessageResponse.buttons` + `chat_messages.buttons_json`.
- ~~**Сон из чата — запись через уточняющий диалог.**~~ Снято 2026-08-30:
  кнопка в трекер закрывает потребность, многоходовый диалог ради записи сна
  не окупается.
- [x] **`education_cta`** *(2026-08-30)*. `context_builder.build_education_cta()` —
  лёгкий проход по RAG (retriever + `_build_rag_grounding_items`), возвращает
  `{type, lesson_id, label}` под фронт (`chat.js appendEducationCta`).
  `SupervisorStage` зовёт его при `reply_card.intent == "education"` и кладёт в
  `SupervisorTurnResult.education_cta` (было захардкожено `None`). Тесты:
  `test_education_cta.py`.
- [x] **Распорядок дня из чата — кнопка в трекер** *(2026-08-30)*. По образцу
  сна: L0 распознаёт отчёт о выполнении распорядка (`_ROUTINE_ENTRY_RE`, intent
  `routine_entry`; отрицание `_ROUTINE_NEGATION_RE` / distress / эмоция / вопрос
  → мимо, к модели). `DataEntryStage` → короткая реплика + кнопка «Открыть
  распорядок дня» (`open_schedule` → `/patient/routine`), без LLM.
  `router_cascade`: `routine_entry` → SIMPLE/LITE. Полная запись в
  `routine.daily_verifications` из чата не собирается (нужны активности плана).
- [x] **`crisis_semantic` — валидация 2026-08-31: НЕ прошёл, удалён.**
  Отчёт `docs/agent/CRISIS_SEMANTIC_VALIDATION.md`. На sha256-pinned golden set рабочей точки
  нет (при терпимом FPR recall {act,plan}/self ≤57%, обрыв диалога на ~30% дистресса).
  Прежний «margin=0.03 → 15/15» (N=15) не воспроизвёлся.
  - [x] `crisis_semantic.py` + `crisis_prototypes.py` + calibrate/build-скрипты +
    тесты + ветка в `boundary_guard` + флаг `LLM_CRISIS_SEMANTIC` — **удалены**.
  - [x] L0 regex — точечная правка: ё/е, «буду прыгать», «отравлюсь таблетками»,
    «сделаю петлю», «нож приготовлен», «раздаю вещи», «уснуть навсегда» и т.д.
    **Recall на golden test 43% → 68%**, FPR не вырос. 187 safety-тестов зелёные.
  - [x] **LLM-классификатор суицид-риска заведён** 2026-08-31 (`app/llm/safety_classifier.py`,
    рубрика из safety-bench, флаг `LLM_SAFETY_LLM` default ON). Градация: plan → обрыв,
    active → агент + жёсткая плашка, passive → агент + мягкая плашка + concern, distress →
    concern. `docs/agent/SAFETY_LLM_INTEGRATION_PLAN.md`.
    - [x] Сверка на **test-сплите** golden set (holdout, L0+LLM): recall
      {act,plan}/self **91%** (было 43–68%), FPR `none` 4% (L0 на слове-теме),
      FPR distress 3%. patient-sim: **0 ложных кризис-эскалаций**. Латентность
      Lite-вызова ~250 мс (serial ок). `docs/agent/PLAN_TOMORROW.md` §NIGHT REPORT.
    - [ ] Снять флаг `LLM_SAFETY_LLM` (как `2316a40`) — решение Дмитрия; цифры на
      holdout позволяют. Опционально: рубрику допилить на «пора заканчивать это
      всё» → `ideation_active` (тюнить на dev).
  - [x] Всё выше **закоммичено и запушено** 2026-09-02: `73daf2c` (safety-слой),
    `29a0820`/`e1edb89`/`704f210`/`196f94d`/`b97be3f` — ветка `feat/agents-rework`.
- [x] **Гигиена.**
  - [x] рейт-лимит на `/api/chat/message` — `app/llm/rate_limit.py` (in-process
    скользящее окно на пациента, `CHAT_RATE_LIMIT_MAX` / `_WINDOW_SEC`) 2026-08-30
  - [x] `GET /api/chat/history` отдаёт `buttons_json` — кнопки (дайджест,
    мотиватор, «Внести данные о сне», «Отменить») восстанавливаются при
    перезагрузке истории (`ChatMessageOut`, 2026-08-30)
  - [x] STRUCTURE.md → 5 стадий (2026-08-29) + daily_context (2026-08-30)
  - [x] `prompts/proactive_anomaly.txt` создан 2026-08-30
  - [x] агент видит `mood_after` практик *(2026-09-02, `e1edb89`)* —
    `context_builder._get_practices_summary` даёт персональную историю за 30 дней
    (что делал / как часто / самочувствие после) + строку «отмечал облегчение
    после: …» при avg(mood) ≥ 2.5; generic-список практик — только новичку
    (< 3 за месяц). `morning_service` / проактив пока видят только счётчик
  - [x] часовые пояса: `get_daily_context_for_llm` + координатор сведены к МСК;
    `motivator._was_motivator_sent_today` → `func.date(func.now())` (часы БД, в
    одном поясе с `created_at`, а не наивное время Python) (2026-08-30).
    `proactive.py` `utcnow()` в дедупе 6ч оставлен — код мёртвый после cutover,
    а `func.now()`-арифметика ломает sqlite-тесты
  - [x] миграция `llm.*.account_id` VARCHAR(20)→(64) *(2026-09-02)*. alembic
    `20260901_01`, применена к `hemo_db` (head `20260901_01`), коммит `704f210`.
    Обе колонки (`llm_request_logs`, `llm_call_log`), модель и срез `[:20]` в
    `pipeline.py` убраны — тег источника раннего ответа пишется целиком.
    `docs/agent/PLAN_TOMORROW.md` §A7.

**Оценка:** 1–2 спринта, задачи независимы. — Фаза 4 закрыта по коду, кроме снятия
флага `LLM_SAFETY_LLM`.

### Фаза 5 — Инструментирование под исследование

**Под заявленную цель платформы** («сбор данных для исследователя»).

- [ ] Что research-панель достаёт из диалогов кроме сырых логов чата.
- [ ] Метрики динамики по пациенту: тональность, темы, вовлечённость, использование
  техник — по времени.
- [ ] Экспорт для анализа.

**Оценка:** 1–2 спринта. Требует постановки от исследователя.

### Фаза 6 — LLM-провайдер: два источника (Cloud.ru + Сбер), переключение флагом

**Решение (2026-09-02):** держать в коде **оба** провайдера и переключать флагом.
Прод по умолчанию — **Cloud.ru** (больше одновременных запросов); Сбер PERS —
переключаемый резерв и источник для тестов/бенчей (бесплатные токены Freemium,
потоки для оффлайн-батча не важны). Плюс — **кнопка в админ-панели** (researcher)
для смены источника Cloud.ru ↔ Сбер без рестарта.

**Провайдеры:**

- **Cloud.ru Evolution Foundation Models** — OpenAI-совместимый шлюз
  `https://foundation-models.api.cloud.ru/v1`, Bearer = ключ `CLOUD_RU_KEY`
  целиком (без обмена на токен). Флагман **GigaChat 3.5 Ultra**
  (`ai-sage/GigaChat3.5-432B-A28B`, 432B/A28B MoE). Цена 3.5 Ultra: **96 ₽/1М
  вход, 289 ₽/1М выход**; есть приветственные токены. Ключ активируется только
  с привязкой **сервиса «Foundation Models» к API-ключу** (роли сервисного
  аккаунта отдельно не хватает). Конкурентность: ~16 параллельных на ключе,
  `429` около 24; несколько ключей под одним аккаунтом квоту не умножают.
- **Сбер GigaChat API** — `GIGACHAT_KEY_A1` (Дима) + `GIGACHAT_KEY_L1` (Лена),
  scope PERS, OAuth через `ngw.devices.sberbank.ru`. С 17.07.2026 базовый адрес
  API — **`https://api.giga.chat`** (старый `gigachat.devices.sberbank.ru` ещё
  жив, но новые модели не отдаёт). Физлицам в **Freemium** доступен
  **GigaChat 3 Ultra** (702B, endpoint `api.giga.chat`, ~1 млн бесплатных
  токенов) — «токены в ЛК появились». Старый endpoint отдаёт только
  Lite/Pro/`GigaChat-2-Max`. ⚠ `api.giga.chat` **не открывается с dev-машины**
  (TLS handshake timeout; старый endpoint работает) — проверить доступность со
  staging/прода до перевода тестов на Сбер-Ultra.

**Проверено 2026-09-02:**

- ⚠ `GigaChat-2-Max` **на Cloud.ru** встроенно цензурирует суицид-контент
  («Извините, не могу ответить») → в safety не годится. **Тот же `GigaChat-2-Max`
  через Сбер** (старый endpoint) цензуру НЕ включает. 3.5 Ultra — чист на обоих.
- **Safety-бенч** (`d:/PROJECT/safety-bench`, golden holdout 181/64, продовая
  рубрика `safety_classifier.txt`, runs=3, t=0):

  | Модель / канал | recall {act,plan} | FPR hard-neg | latency p50 |
  |---|---|---|---|
  | **GigaChat 3.5 Ultra · Cloud.ru** | **0.97** [0.92, 1.00] | **0.00** | 744 мс |
  | GigaChat-2-Pro · Сбер | 0.86 [0.77, 0.94] | 0.00 | 471 мс |
  | GigaChat-2 Lite · Сбер (прод сейчас) | 0.78 [0.67, 0.88] | 0.02 | 223 мс |

  Разрыв — модель, не рубрика (все три по одному тексту). 3.5 Ultra стабилен при
  t=0 (0.97/0.97/0.97), немых пропусков ноль. Особенность — перестраховка на
  границе passive→active (6/37: кластер «пора прекратить всё это» → жёсткая
  плашка вместо мягкой); при желании тюнится рубрикой на dev.
- GigaChat 3 Ultra через Сбер на бенче **не прогнан** — endpoint недоступен
  с dev-машины (см. выше).

**Задачи:**

- [x] **Cloud.ru-клиент в `app/llm/pool.py`** *(2026-09-03)*. `ProviderSpec`
  (адрес / OAuth-или-нет / имена моделей / серверные заголовки), `SBER` +
  `_cloudru_spec()`; `GigaChatClient` провайдер-осознанный (`_get_access_token`
  для cloudru = ключ как есть, `_execute` по `provider.chat_url`). `AccountPool`
  строит клиентов ОБОИХ провайдеров сразу (Сбер из `GIGACHAT_KEY_*`, Cloud.ru из
  `CLOUD_RU_KEY` на `Semaphore(CLOUD_RU_CONCURRENCY)`). Cloud.ru: `response_format`
  в OpenAI-каноне (`structured.response_format_for(provider=)` — плоская
  сберовская форма даёт 400). E2E проверен: `call()`/`structured()` sub-second,
  верная классификация. Тесты `test_pool.py` (+7).
- [x] **Флаг `LLM_PROVIDER`** (`sber` default | `cloudru`) *(2026-09-03)*.
  `.env.example` + Cloud.ru-секция (`CLOUD_RU_KEY`, `CLOUD_RU_MODEL[_TIER]`,
  `CLOUD_RU_CONCURRENCY`). `get_available(provider=)` — оверрайд; `embeddings.py`
  прибит к `provider="sber"` (индекс на модели `Embeddings`).
  `scheduler._PROACTIVE_CONCURRENCY = pool.proactive_concurrency`.
  ⚠ default `sber` — на мерже поведение не меняется; прод переводится
  `LLM_PROVIDER=cloudru` в env после проверки agent/кэша.
- [x] **Переключатель в админ-панели** *(2026-09-03)*. Универсальная таблица
  `public.app_settings` (key/value/updated_at/updated_by, миграция `20260903_01`,
  **применена к `hemo_db`**); доступ — `app/core/app_settings.py`. `AccountPool`:
  `set_active_provider()` меняет активного в рантайме без пересборки (клиенты
  обоих провайдеров уже в пуле), отклоняет провайдера без ключа. Эндпоинты
  `GET/POST /api/v1/researcher/llm-provider` (`get_current_researcher`, пишет
  `updated_by`). Lifespan `app/main.py` применяет сохранённый выбор на старте
  (пусто → `LLM_PROVIDER` из env). Фронт: виджет `js/llm_provider.js` (сегмент
  Сбер|Cloud.ru + строка «источник/кто менял») на **дашборде** и в **отладочном
  чате** (`data-llm-provider`). Тесты `test_llm_provider.py` (+3). ⚠ фронт
  кликом в браузере не гонял — эндпоинт-контракт проверен.
- [~] **Сбер на новый endpoint.** Адрес чата вынесен в `GIGACHAT_CHAT_URL`
  (default — старый рабочий endpoint). Со staging: выставить
  `https://api.giga.chat/v1/chat/completions`, проверить, добавить модель
  GigaChat 3 Ultra в `MODEL_NAMES` (сейчас там только gen-2). `safety-bench/
  sbench/gigachat.py` — тем же env. Блокер: `api.giga.chat` не открывается с dev.
- [x] **safety-классификатор на выбор провайдера** *(2026-09-03)*.
  `safety_classifier.classify()`: тир `max` при `pool.chat_provider == "cloudru"`
  (→ `CLOUD_RU_MODEL_MAX`, GigaChat 3.5 Ultra), иначе `lite` (GigaChat-2 Lite,
  Сбер — прод-конфиг без изменений). `_RiskCard.confidence` → `Literal[low|
  medium|high]` (свободный float у 3.5 через grammar-decoder «убегал»).
  **`structured.response_format_for`**: все поля в `required` + снят `default` —
  иначе decoder Cloud.ru после необязательного поля залипал на whitespace до
  обрыва по max_tokens. **Eval на test-сплите (holdout) через Cloud.ru: recall
  {act,plan}/self 98.2 % (54/55), passive-recall 100 %, 0 repair'ов.** FPR none
  4 % и FPR other/abstract 21 % — **всё L0** (regex по слову-теме: «муж собирается
  уйти из жизни», «подруга напишет что будет прыгать»), классификатор на
  other/abstract чист (0). Т.е. «3.5 граббовее» относилось к агенту, не к
  классификатору.
- [x] **Реактивный агент (`SupervisorStage` / `agent/loop.py`) на Cloud.ru**
  *(2026-09-03)*. Tool-calling: `ProviderSpec.tool_protocol` (`sber`:
  `functions`/`function_call`/`role=function`; `openai`: `tools`/`tool_choice`/
  `role=tool`/`tool_calls`). `call_with_functions` строит payload и парсит ответ
  по протоколу; `FunctionCall.call_id` (OpenAI tool_call_id);
  `GigaChatClient.tool_exchange_messages()` собирает пару «вызов+результат»
  в формате провайдера — `agent/loop.py` зовёт её вместо инлайна. E2E на
  Cloud.ru: структурный `AgentReply` — 0 repair; tool-roundtrip (search_education)
  отрабатывает; **префиксный кэш 99.7 %** (`precached=323/324` со 2-го хода,
  без прогрева, телеметрия `prompt_tokens_details.cached_tokens` ловит).
- [x] **Телеметрия** *(2026-09-03)*. `llm_call_log` уже пишет `account_id`
  (`cloudru-max` / `A1-lite` — канал по префиксу) + `model` (реальный id) +
  `precached_tokens` (Cloud.ru-кэш ловится из `prompt_tokens_details`). Активный
  провайдер на дашборде — виджет `llm_provider.js` (шаг 2).
- [x] **Цена** *(2026-09-03)* — `docs/agent/CLOUDRU_COST_ESTIMATE.md`. ~1.18 ₽/
  сообщение при кэше по полной ставке, ~0.29 ₽ при кэше −90 % (политика биллинга
  кэша Cloud.ru не опубликована — спросить поддержку). Пилот 20 пациентов ≈
  2.6–10.6 тыс ₽/мес, 50 ≈ 6.5–26.5 тыс. Порядок комфортный. Осталось:
  спросить про кэш + запросить повышение RPM/TPM.
- [x] **patient-sim на Cloud.ru** *(2026-09-03, `--quick`)*: **6 PASS / 1 WARN /
  1 FAIL**. FAIL — `s05_anxious`: GigaChat 3.5 (как агент) эскалирует на
  катастрофизации здоровья («я так и умру здесь одна с этим комом в горле»).
- [x] **De-escalation слой против перестраховки агента** *(2026-09-03)*.
  Не промпт-патч, а обвязка: `router_l0.looks_like_health_catastrophizing()` —
  триплет (смерть-слово + гипотетическая рамка `а вдруг`/`а если` + мед-контекст
  `шунт`/`фистула`/`осложнение`/…). `_apply_agent_safety_net`: единоличный
  `urgent` агента → `concern` (мягкая плашка, ответ агента не выброшен), **если
  ни L0, ни классификатор его не подтвердили**. Обрыв остаётся при согласии
  хоть одного эшелона. Триплет не задевает ни реальный суицид («зачем всё это
  тянуть»), ни реальную мед-неотложку («давление рухнуло, кажется умру» — нет
  гипотетики). Тесты: `test_router_l0_safety.py` (+9), `test_single_agent.py`
  (+4). Живой прогон исходного s05-текста через пайплайн на Cloud.ru: агент
  трижды даёт `urgent`, гейт трижды понижает до `concern` (grounding-техника
  вместо хотлайн-протокола).
- [~] **Полный patient-sim на Cloud.ru** *(2026-09-03, 29 перефразировок)*:
  **24 PASS / 1 WARN / 4 FAIL**. Recall цел — s01 7/7, s02 6/6. Здоровье-тревога
  ходы 1–2 закрыты де-эскалацией. Остатки (мельче, не блокеры):
  - `s05` ход 3 — (a) агент эскалирует на фрустрации без кризиса («дай конкретику
    про кнопку вызова»); ~~(b) голое «если давление рухнет» проскакивает мимо
    `_is_hypothetical_question` L0~~ — **закрыто `e035ef9`**: `_HYPOTHETICAL_MARKER_RE`
    +ветка «если …рухнет/встанет/забьётся/не выдержит/откажет» без «а»/«вдруг»
    (`test_router_l0_safety.py` +5);
  - `s07` — **не регрессия**: динамический пациент раскрутил сценарий в реальную
    мед-неотложку («ноги раздуло, дышать нечем, сахар 16»), `boundary_guard=
    urgent(medical)` → 103 — верно. Реальный мисс один: «можно инсулина добавить,
    пока скорая едет» → бот дал психологический хотлайн вместо «не советую по
    дозам, дождись скорую». + эвристика patient-sim не различает мед-эскалацию
    (ок) и ложный психокризис.

**Оценка:** осталось — Сбер-endpoint (когда откроется api.giga.chat), опц.
разнести кризис-шаблоны psych/medical на ходе «пока скорая едет». **Прод
переключается флагом/кнопкой — решение за исследователем.**

### Сквозное — тесты

Добавляются вместе с каждой фазой:

- **Фаза 1:** [x] тест триггера входа
  (`tests_py/routers/test_login_proactive_trigger.py` — гейт + планирование фон-задачи;
  `tests_py/llm/test_morning_trigger.py`, `test_on_login.py` — своя сессия + глушение
  ошибок + порядок утро→мотиватор; отсечка по времени/дню — внутри
  `ensure_morning_message`, Postgres-only); [x] тест `mark-read`
  (`tests_py/routers/test_chat_mark_read.py`).
- **Фаза 2:** [x] `proactive.py` (`test_proactive.py` — очередь, приоритет,
  потолок 3, дедуп 6ч, `is_read=False`, холодный старт); [x] координатор
  (`test_proactive_coordinator.py` — ранжирование, потолок, `allow_llm`,
  дедуп-леджер, cold-start gate); [x] холодный старт (`test_morning_service.py`);
  [x] `get_daily_context` в волатильном слое (`test_single_agent.py`);
  [x] 429-backoff (`test_http_policy.py`).
- **Фаза 6:** [x] пул двух провайдеров (`test_pool.py` +7 — оба клиента в пуле,
  `response_format` в OpenAI-каноне, `set_active_provider`); [x] переключатель
  в researcher-панели (`tests_py/researchers/test_llm_provider.py` +3 —
  эндпоинт-контракт, `updated_by`); [x] L0-гард здоровье-тревоги
  (`test_router_l0_safety.py` +9 +5); [x] safety-net понижение `urgent`→`concern`
  (`test_single_agent.py` +4). Eval safety-классификатора на holdout через
  Cloud.ru — `scripts/eval_safety_classifier.py` (не pytest).
- **Общий:** [x] сквозной тест пайплайна с моком GigaChat
  (`tests_py/llm/test_pipeline_e2e.py`, 2026-08-30) — реальные 5 стадий, GigaChat
  замокан на `pool.get_available`; 7 сценариев: кризис / медицинский urgent /
  запись АД / сон-кнопка (ранние ответы, модель не зовётся), полный проход
  (5 стадий, 1 вызов), safety-net override, откат при сбое схемы.

## Спринт 1 — «Проактив запускается и доходит до пациента при входе»

**1 неделя, один разработчик.**

**Цель спринта:** пациент, зайдя в систему, получает утреннее проактивное
сообщение; бейдж ассистента корректно сбрасывается; мы знаем, на какой модели
реально работает агент и окупается ли префиксный кэш.

**Итог (2026-08-29):** весь код и тесты готовы (тестовый прогон — 441 passed),
investigation-отчёты приложены (`SPRINT1_INVESTIGATIONS.md`). Открыто одно:
smoke на staging для #4 (планировщик под `--workers`) и #5 (E2E логин → дайджест).
Локально оба пути проверены (планировщик поднимается за флагом, `ensure_morning_message`
идемпотентен на dev-Postgres).

Статус: ✅ готово · 🟡 код готов, ждёт staging-smoke · ⬜ не начато.

| # | ✔ | Тип | Задача | Оц., дн |
|---|---|---|---|---|
| 1 | ✅ | invest. | Аудит аккаунта GigaChat → `SPRINT1_INVESTIGATIONS.md` §1. Pro/Max работают; лимит потоков = 1 на ключ. *(2026-09-02: заказчик добавил 2-й ключ `GIGACHAT_KEY_L1`; пул обобщён под N ключей, конкурентность = 2)* | 0.5 |
| 2 | ✅ | invest. | Замер `cache_hit` → `SPRINT1_INVESTIGATIONS.md` §2. Тёплый ход 80 %, префикс стабилен | 0.5 |
| 3 | ✅ | fix | `POST /api/chat/mark-read` + `proactive.py` → `is_read=False`. Тесты | 0.5 |
| 4 | 🟡 | feat | Планировщик в lifespan `app/main.py` за `SCHEDULER_ENABLED`; advisory-lock из `worker.py` туда же; `SCHEDULER_ENABLED` + `LLM_CRISIS_SEMANTIC` в `.env.example`; smoke в staging | 1.0 |
| 5 | 🟡 | feat | Триггер `ensure_morning_message` из `patient_login` (`BackgroundTasks`) + ленивый из `GET /api/chat/history`. Тест идемпотентности | 1.5 |
| 6 | ✅ | fix *(stretch)* | Сон из чата: SLEEP убран из `router_l0.parse_vitals` + `data_entry`. Не обещаем запись, которой нет. Тесты | 0.5 |

**Итого:** ~4.5 дня основного + 0.5 stretch.

**Definition of done:**

- [ ] На staging: включённый флаг → при логине тестового пациента в
  `llm.chat_messages` появляется сообщение `request_type='morning'`; повторный
  логин в тот же день дубля не создаёт.
- [ ] Открытие чата → `mark-read` → бейдж `assistant` в сайдбаре гаснет.
  *(эндпоинт готов, проверка на staging — при закрытии спринта)*
- [x] Отчёты по задачам 1–2 приложены к спринту — `SPRINT1_INVESTIGATIONS.md`.
  Вывод по #1: Pro/Max работают. *(2026-09-02: заказчик добавил 2-й ключ
  `GIGACHAT_KEY_L1`; `AccountPool` обобщён под N ключей, конкурентность = 2 —
  дополнение к §1.)*
- [x] `worker.py` не удаляем (запасной путь), но в проде на одном инстансе не
  используется.

**Явно вне спринта 1:** координатор, позитивная аналитика,
`get_daily_context_for_llm`, `education_cta`, routine из чата,
тесты `proactive.py`, обновление STRUCTURE.md.

## Спринт 2 — предварительно

- [x] Хвост Фазы 1 *(2026-08-29)*: `motivator` на ленивый вызов при входе
  (`app/llm/on_login.py`); тесты `proactive.py` (`test_proactive.py`);
  STRUCTURE.md → 5 стадий + `DataEntryStage` + замер кэша. `proactive` (LLM-путь)
  на ленивый вызов **не** переведён — сознательно, см. Фазу 1.
- [x] Старт Фазы 2: каркас координатора *(2026-08-29)* —
  `app/llm/proactive_coordinator.py` (collect → select → deliver, дедуп-леджер
  `llm.proactive_deliveries`, потолок 2/день), ORM-модель + миграция
  `20260829_01` (применена), 9 тестов. Дедуп — **отдельная таблица**.
- [x] Позитивная аналитика недели *(2026-08-29)* — `morning_service`.
- [x] Cutover координатора *(2026-08-30)*: `scheduler` (5 → 3 джобы) и
  `on_login` переведены; `domain_scorer` подключён; `get_daily_context_for_llm`
  в супервизоре; холодный старт; лимит GigaChat (семафор + 429-backoff).
  **Фаза 2 закрыта по коду.** Осталось: staging-smoke → снести старые `deliver_*`.

## Спринт 3 — предварительно

- [ ] Staging-smoke Фаз 1–2 (флаг → логин → координатор → дайджест; cron-проходы;
  дедуп). После — удалить `deliver_morning_message` / `deliver_proactive_messages`
  / `deliver_motivator_messages` / `ensure_morning_message_bg` /
  `deliver_motivator_messages_bg` и их тесты.
- [ ] Снять флаг `LLM_SAFETY_LLM` после живой проверки классификатора.
- [x] ~~Фаза 4 остаток: `crisis_semantic`, миграция `account_id`~~ — закрыто
  2026-08-31…09-02 (слой удалён + LLM-классификатор; `account_id` применена).
- [x] ~~Фаза 6: два LLM-провайдера (Cloud.ru + Сбер) в `app/llm/pool.py`, флаг
  `LLM_PROVIDER` + переключатель в researcher-панели, перевод safety-классификатора
  и реактивного агента на GigaChat 3.5 Ultra~~ — **код готов 2026-09-03**
  (`1729e7d`..`e035ef9`), миграция `20260903_01` применена. Хвост: Сбер на
  `api.giga.chat` (заблокировано с dev), прод-cutover флагом/кнопкой (решение
  исследователя).
- [ ] Фаза 5: инструментирование под исследование (нужна постановка).

## Приложение — связь с находками аудита

| ✔ | Находка аудита | Фаза |
|---|---|---|
| 🟡 | Проактив не запущен (`SCHEDULER_ENABLED`) | 1 |
| 🟡 | Нет триггера «при первом входе» | 1 |
| ✅ | `/api/chat/mark-read` отсутствует, бейдж не сбрасывается | 1 |
| ✅ | Пул GigaChat: один ключ в 3 тира, конкурентность = 1 | 0 — диагностирован; +2-й ключ Сбера (2026-09-02); стратегически → Cloud.ru (Фаза 6) |
| 🟡 | LLM-провайдер: два источника (Cloud.ru + Сбер), флаг + кнопка в админке | 6 — **код готов 2026-09-03** (`1729e7d`..`e035ef9`): Cloud.ru-клиент, флаг `LLM_PROVIDER` (default `sber`), переключатель в researcher-панели, миграция `20260903_01` применена; safety-классификатор + реактивный агент работают на 3.5 Ultra. Бенч: recall safety 0.78 → 0.97. Хвост: Сбер-endpoint, прод-cutover |
| ✅ | Кэш: наблюдаемости нет | 0 — замерен (тёплый ход 80 %), `SPRINT1_INVESTIGATIONS.md` §2 |
| ✅ | Три проактивные подсистемы без координатора | 2 — координатор + cutover, 2026-08-30 |
| ✅ | Аналитика недели только через проблемы | 2 — `_build_achievement_lines` + `achievement_summary` перед проблемными строками (2026-08-29) |
| ✅ | `get_daily_context_for_llm` не вызывается | 2 — в `SupervisorStage`, волатильный слой (2026-08-30) |
| ✅ | Холодный старт: доменные сообщения «из ничего» | 2 — `has_tracked_data` гейт + приветствие (2026-08-30) |
| ✅ | Канала доставки проактива нет | — доставка только веб (сообщение ждёт в истории чата); внешний канал снят с плана 2026-08-30 |
| ✅ | Сон из чата: «сказал записал — не записал» | 1 — ложный «Записал» убран + кнопка в трекер сна (2026-08-30); запись через диалог снята из плана |
| ✅ | `education_cta` захардкожен `None` | 4 — `build_education_cta` + вызов в супервизоре (2026-08-30) |
| ✅ | Распорядок дня из чата не вносится | 4 — кнопка в трекер по образцу сна (2026-08-30) |
| ✅ | `crisis_semantic` выключен флагом | 4 — валидация провалена, слой **удалён** 2026-08-31; L0 regex усилен + заведён **LLM-классификатор** (`safety_classifier.py`, golden test-сплит recall {act,plan}/self 91%, patient-sim 0 ложных). Осталось снять флаг. `docs/agent/CRISIS_SEMANTIC_VALIDATION.md`, `docs/agent/SAFETY_LLM_INTEGRATION_PLAN.md` |
| ✅ | `account_id` VARCHAR(20) | 4 — расширена до VARCHAR(64), alembic `20260901_01` применена 2026-09-02, коммит `704f210` |
| ✅ | Рейт-лимита на `/api/chat/message` нет | 4 — `app/llm/rate_limit.py` (2026-08-30) |
| ✅ | STRUCTURE.md отстал (4 стадии vs 5) | 4 — обновлён 2026-08-29 (5 стадий, `DataEntryStage`, вх. контракт, замер кэша) + daily_context 2026-08-30 |
| ✅ | отсутствует `prompts/proactive_anomaly.txt` | 4 — создан 2026-08-30 |
| ⬜ | Research-инструментирование диалогов | 5 |

---

*Обновлять по итогам каждого спринта: отмечать закрытые задачи, переносить
хвосты, уточнять оценки следующих фаз.*
