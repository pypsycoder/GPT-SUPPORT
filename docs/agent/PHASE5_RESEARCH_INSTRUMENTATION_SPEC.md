# Фаза 5 — Инструментирование под исследование: ТЗ

**Дата:** 2026-09-17, реализация 2026-09-18
**Статус:** реализовано полностью — Track A, B, C. Миграции `20260917_01`,
`20260918_01` применены к `hemo_db` (Track C своей миграции не требует — поля
`consent_personal_data`/`consent_bot_use` уже существовали, просто не
проверялись). Полный прогон тестов зелёный (606 passed, 2 skipped).
**Основание:** `ROADMAP_AGENT.md` → Фаза 5 (была стабом, «требует постановки от
исследователя»); аудит текущего `researchers/`-модуля и LLM-данных (2026-09-17).

## Контекст — что уже есть сейчас

- `app/researchers/router.py` (~1080 строк, **без `service.py`** — бизнес-логика
  прямо в роутере, отклонение от стандартного паттерна модуля):
  `/chat-logs` (просмотр сырых логов), `/chat-stats` (агрегаты: токены, домены,
  активность по часам/дням), `/chat-logs/export` (CSV/JSON, единственный
  существующий экспорт), `/chat-debug/*` (песочница, не реальный трафик),
  `/stats`, `/cohorts`.
- Шкалы (`scales.scale_results`): ответы на отдельные вопросы уже пишутся в
  `answers_json` (JSON-блоб) для HADS/KOP-25A/PSQI/PSS-10/WCQ, рядом с итогом в
  `result_json`. KDQOL-SF — единственная нормализованная: `kdqol.kdqol_responses`
  (по строке на вопрос).
- LLM-данные (`app/models/llm.py`): `chat_messages` знает `domain`/`request_type`,
  но **`safety_level` и `technique_id` нигде не персистятся** — считаются в
  рантайме и теряются. `llm_request_logs.diagnostics_json` — свободный
  неструктурированный bag, не рассчитан на массовый анализ.
- Consent (`app/consent/`) — **чисто декоративный**: `get_current_user`
  (`app/auth/dependencies.py`) не проверяет `consent_personal_data` /
  `consent_bot_use`; ни один защищённый роут (включая `/api/chat/message`) не
  блокирует доступ без согласия. Фронт (`onboarding.js`) уже редиректит на
  `/consent`, если `!consent_personal_data`, до онбординга — серверный гейт
  просто закрывает дыру, порядок не меняет.
- Практики: две параллельные таблицы — `practices.practice_completions`
  (standalone-модуль) и `education.practice_logs` (привязан к урокам).
- Медикаменты: adherence нигде не посчитан — только сырые
  `medication_prescriptions` / `medication_intakes`.

## Зафиксированные решения (2026-09-17)

| Вопрос | Решение |
|---|---|
| Per-item ответы шкал (не-KDQOL) | Нормализовать в новую таблицу `scales.scale_item_responses`, по образцу `kdqol_responses`. Писать **параллельно** с `answers_json` — существующий контракт `scales/` (production-ready) не трогаем |
| Consent-гейт | Два независимых флага: `consent_personal_data` — блокирует весь сайт, `consent_bot_use` — отдельно чат |
| Способ выдачи данных исследователю | Оба: CSV/JSON-экспорт в панели (расширение паттерна `/chat-logs/export`) **и** read-only paginated JSON API для программного доступа |
| Источник статистики практик | Обе таблицы вместе (`practices.practice_completions` UNION `education.practice_logs`), с полем-источником в ответе |
| Adherence по лекарствам | Простая метрика: `count(medication_intakes)` в день vs `frequency_times_per_day`, без матчинга по `intake_slot` |
| Механизм consent-гейта | Dependency (правка `get_current_user` + `get_current_user_raw` для исключений) — не middleware. Совпадает с тем, как уже устроена авторизация в проекте (единственный существующий middleware — `CORSMiddleware`) |
| Ретроспектива / backfill | Не нужен — в чате пока только тестовые пациенты |

## Track A — Статистика и экспорт трекеров/шкал

1. **Шкалы.** Миграция: `scales.scale_item_responses` (`result_id` FK →
   `scale_results.id`, `question_id`, `answer_value`, `measured_at`). Запись —
   в `scales/services.py`, в том же вызове, что сейчас пишет `answers_json`
   (не заменяет его). Без backfill.
2. **Медикаменты — adherence.** Новый сервис: `% дней`, где
   `count(medication_intakes для дня)` ≥ `frequency_times_per_day`
   предписания, действовавшего в этот день.
3. **Практики.** Объединённая выборка обеих таблиц с полем-источником
   (`standalone` / `lesson`), чтобы не путать при анализе.
4. **Уроки/тесты, сон, витальные.** Уже плоские/готовые данные — только
   экспорт-слой поверх существующих таблиц (`lesson_test_results.answers_json`
   уже содержит ответ на каждый вопрос теста).
5. **Архитектурная правка.** `app/researchers/` не соответствует паттерну
   модуля из `CLAUDE.md` (нет `service.py`). Новую логику (adherence,
   объединение источников, агрегации) выносим в новый
   `app/researchers/service.py` — не множим бизнес-логику в роутере дальше.
6. **Выдача:**
   - CSV/JSON-экспорт в `researchers/router.py`, по образцу
     `/chat-logs/export`, под каждый домен (медикаменты, шкалы, практики,
     уроки/тесты, сон, витальные);
   - read-only paginated JSON: `GET /researchers/{domain}/records`
     (`patient_id`, `date_from`, `date_to` — общий контракт фильтров, как у
     `/chat-logs`);
   - отдельный `GET /researchers/scales/items` — длинный формат
     (`patient_id`, `scale_code`, `scale_version`, `measured_at`,
     `question_id`, `answer_value`) для КОП-25/KDQOL и остальных шкал одним
     контрактом.

## Track B — Инструментация диалога (сырой + решения алгоритма)

**Реализовано иначе, чем в исходном плане ниже — проще и с тем же результатом.**
Изначально планировалась отдельная таблица 1:1 к `chat_messages`. По факту
`llm.llm_request_logs` уже пишется ровно раз на ход пайплайна (и для
реактивного `/api/chat/message`, и для LLM-проактива через
`proactive_coordinator._render_via_pipeline` — оба зовут один и тот же
`LLMPipeline.process()`) и уже содержала колонку `diagnostics_json`, которая
на боевом пути просто никогда не заполнялась. Вместо новой таблицы:

- `LLMPipeline._log_to_database` (`app/llm/pipeline/pipeline.py`) теперь пишет
  туда весь `context.diagnostics` целиком (решения каждой стадии — boundary_guard,
  classification, supervisor, safety_net — без потери детализации);
- три новые плоские колонки поверх него для быстрой фильтрации/статистики:
  `response_source` (какая стадия дала ответ — `supervisor` /
  `boundary_guard_crisis` / `boundary_guard_medical_urgent` /
  `boundary_guard_safety_llm` / `data_entry` / `error_fallback` / …),
  `technique_id` (из `diagnostics.supervisor.agent.technique_id`),
  `safety_level` (`diagnostics.supervisor.safety_net.agent_level`, если ход
  дошёл до супервизора, иначе `context.l0.safety_level` — раздельно, потому что
  `diagnostics["boundary_guard"]` не содержит ключа `level` на самом частом,
  L0-кризисном пути, только в ветке LLM-классификатора);
- миграция `20260918_01_add_trace_columns_to_llm_request_logs.py` (применена).

Экспорт: `/researcher/chat-logs` и `/researcher/chat-logs/export` расширены
тремя новыми колонками + `diagnostics_json` в export (гейтится тем же
`include_content`, что и текст сообщений).

**Сознательно не реализовано** (не входило в риск/выгоду этого шага, тянет за
собой более глубокие правки хот-пути агента):
- `tool_calls` — вызовы инструментов агента (`agent/loop.py`) нигде не
  персистятся структурно, только счётчик `tool_hops` в diagnostics; имя/аргументы
  инструмента сейчас нигде не сохраняются;
- `cache_hit` — есть только на уровне отдельного HTTP-вызова
  (`llm.llm_call_log.precached_tokens`), не на уровне хода; join с этой
  таблицей по `patient_id`+`session_key`+времени возможен, но неточный (не
  делали).

Исходный план (для истории):

- `message_id`, `patient_id`, `created_at`
- `boundary_guard_decision`, `domain`, `request_type`, `intent`
- `safety_level_raw` / `safety_level_final` / `safety_source`
- `technique_id`, `technique_step_index`
- `stage_path`, `model`, `provider`, `tier`, `tokens_in`, `tokens_out`,
  `latency_ms`, `cache_hit`, `tool_calls`, `education_cta`

## Track C — Consent gate (сервер) — реализовано

- `consent_personal_data` → гейтит весь сайт. `get_current_user`
  (`app/auth/dependencies.py`) теперь требует его — на эту dependency уже
  завязаны 12+ модулей (medications/vitals/education/practices/sleep/scales/
  routine/profile/notifications/chat/...), правка в одном месте закрыла их все.
  Новая `get_current_user_raw` (без проверки) — под ней остались только
  исключения: `GET /auth/patient/me` (иначе фронт не узнает свой
  consent-статус, чтобы решить, вести ли на `/consent`), `/consent/status`,
  `/consent/accept`, `/consent/revoke`. `/auth/patient/logout` и так не
  использовал `get_current_user` (читает cookie напрямую) — исключать не
  пришлось. `/auth/patient/onboarding/complete` **не** исключён: по текущему
  фронт-флоу (`onboarding.js`) до онбординга пациент уже обязан пройти
  `/consent`, так что обычный `get_current_user` там ничего не блокирует.
  Роуты исследователя (`get_current_researcher`) — отдельный auth-контур, не
  затронуты.
- `consent_bot_use` → отдельная обёртка `get_current_user_with_bot_consent`
  (оборачивает `get_current_user`, т.е. требует оба согласия), применена ко
  **всем** эндпоинтам `app/routers/chat.py` (`/message`, `/history/{id}`,
  `/mark-read`, `/confirm-vitals`, `/undo-vitals`, `/reset-session`,
  `/pool/stats`).
- Контракт отказа: `403`, тело — **строка** `"consent_required:personal_data"`
  или `"consent_required:bot_use"` (не dict, как планировалось изначально) —
  в проекте уже есть общий exception handler (`app/api_errors.py`), который
  для non-string `detail` подставляет generic `"Request failed"` и теряет
  структуру; тип согласия закодирован префиксом в строке вместо отдельного
  поля.
- **Фронт не трогали.** Проверено: `login.js` уже редиректит на `/consent`
  сразу после логина, если `needs_consent` — обычная навигация никогда не
  доходит до гейта. `consent.js` всегда шлёт оба согласия одним запросом
  (`consent_personal_data: true, consent_bot_use: true`) — комбинация
  personal_data=true/bot_use=false недостижима через штатный UI, так что
  `consent_bot_use`-гейт в чате не создаёт нового пользовательского сценария
  ошибки. 403 — защита от прямых вызовов API в обход интерфейса, не основной
  UX-механизм.
- Тесты: `tests_py/auth/test_auth_api.py` (+3 — 403 на защищённом роуте без
  согласия, `/auth/patient/me` и `/consent/*` работают без согласия, `/accept`
  снимает гейт), `tests_py/routers/test_chat_mark_read.py` (+1 —
  `consent_bot_use` гейтит чат отдельно от `consent_personal_data`).

## Не входит в Фазу 5

- Backfill/ретроспектива — не нужны (только тестовые пациенты в чате).
- Слияние `practices.practice_completions` и `education.practice_logs` в одну
  таблицу — только `UNION` на чтение, схемы не трогаем.
- UI-виджеты под новые домены на фронте researcher-панели — только
  эндпоинты + CSV; если понадобится визуализация — отдельная задача.
- Crisis-aware gating проактива (упомянуто в
  `SAFETY_LLM_INTEGRATION_PLAN.md` §6.2) — не сюда.

## Открытые технические детали (не блокируют старт реализации)

- Alembic-миграции (новая таблица `scale_item_responses`, новая таблица трассы
  диалога) — по явному запросу отдельно, не автогенерятся молча
  (`CLAUDE.md` правило 1, порядок — `ALEMBIC_RUNBOOK.md`).
- Точный нейминг новых эндпоинтов — уточняется в процессе реализации, контракт
  фильтров уже задан выше.
- Нужно свериться, есть ли у онбординга собственные API-шаги до
  `consent.accept` (кроме `/auth/patient/onboarding/complete`), которые тоже
  потребуют `get_current_user_raw`.
