# Tech Debt Roadmap

Этот файл нужен как живой контекст между чатами и спринтами.

Правила работы:
- Один спринт = один чат.
- По завершении задач в спринте отмечаем чекбоксы.
- После завершения спринта обязательно проводим тестовый прогон и фиксируем результат в этом файле.
- Новый чат начинается с чтения этого файла и выбора следующего незавершённого спринта.

---

## Sprint 1. Config + Startup/Scheduler + Test Harness

Цель:
- стабилизировать runtime-конфигурацию;
- убрать side effects на импорт/стартап;
- сделать тестовый контур предсказуемым.

### 1. Runtime config consolidation
- [x] Ввести единый источник правды для настроек приложения.
- [x] Убрать дублирующийся `load_dotenv` из runtime-модулей.
- [x] Оставить загрузку `.env` только в явных entrypoint/bootstrap-точках.
- [x] Разделить `dev` / `test` / `prod` конфигурации.
- [x] Зафиксировать обязательные env-переменные и fail-fast поведение.

### 2. Startup / DB init / Scheduler separation
- [x] Убрать создание схем БД из startup API-приложения.
- [x] Перенести структурную инициализацию БД в migrations/init command.
- [x] Убрать автозапуск scheduler из API-процесса.
- [x] Вынести scheduler в отдельный entrypoint / worker.
- [x] Добавить явный флаг включения scheduler.
- [x] Сделать запуск scheduler безопасным для multi-worker/multi-instance сценариев.

### 3. Test harness cleanup
- [x] Удалить кастомный async-hook из `tests/conftest.py`.
- [x] Перевести async-тесты на штатный `pytest-asyncio`.
- [x] Разделить `unit` и `integration` тесты.
- [x] Привести фикстуры БД к одному предсказуемому паттерну.
- [x] Зафиксировать базовую команду запуска тестов для спринта.

### Definition of done
- [x] У проекта один источник runtime-настроек.
- [x] API стартует без скрытых DB/scheduler side effects.
- [x] Тесты запускаются штатно и воспроизводимо.

### Sprint test / verification
- [x] Локально/в CI проверен старт API без автозапуска scheduler.
- [x] Проверен отдельный запуск scheduler worker.
- [x] Прогнан целевой набор unit/integration тестов спринта.
- [x] Результат теста и замечания зафиксированы ниже.

### Notes
- Статус: `done`
- Дата начала: `2026-04-04`
- Дата завершения: `2026-04-04`
- Итог теста: `pytest -m unit` -> 17 passed, `pytest -m integration` -> 5 passed
- Замечания:
  - Единый runtime-config: `app/core/config.py`; `.env` грузится только в entrypoint/скриптах.
  - API больше не создаёт схемы БД и не запускает scheduler на старте.
  - Scheduler вынесен в `python -m app.llm.worker`, включается только при `SCHEDULER_ENABLED=true`, защищён Postgres advisory lock.
  - Инициализация схем вынесена в явные команды `scripts/init_db_from_models.py` / `scripts/init_tables.py`; структурные изменения ожидаются через Alembic.
  - Базовые команды спринта: `pytest -m unit` и `pytest -m integration`.
---

## Sprint 2. API Consistency + Auth Hardening + Permissions Tests

Цель:
- привести API к единому контракту;
- укрепить auth/session lifecycle;
- закрыть критичные permission-сценарии тестами.

### 1. API consistency
- [x] Принять единое правило для базовых API-префиксов.
- [x] Унифицировать использование `/api` и `/api/v1`.
- [x] Нормализовать router prefixes: один источник сборки маршрутов.
- [x] Ввести единый response/error pattern.
- [ ] Согласовать контракт с frontend и переходный путь при необходимости.

### 2. Auth hardening
- [x] Добавить lifecycle-поля для сессий (`revoked_at`, `last_seen_at` и др. по согласованной модели).
- [x] Добавить cleanup expired/revoked sessions.
- [x] Определить и реализовать стратегию session rotation.
- [x] Нормализовать cookie policy по окружениям.
- [x] Принять и задокументировать optional CSRF strategy для sensitive flows.
- [x] Добавить/уточнить audit fields для auth-related сущностей.

### 3. Permissions and auth tests
- [x] Покрыть happy-path сценарии авторизации пациента и исследователя.
- [x] Покрыть deny-path сценарии авторизации и access control.
- [x] Добавить тесты на expired/revoked sessions.
- [x] Добавить тесты на logout / cleanup / session lifecycle.
- [x] Добавить тесты на permissions boundaries между ролями.
- [x] Добавить тесты на profile/auth-sensitive endpoints.

### Definition of done
- [ ] API-контракт стал единообразным.
- [x] У сессий есть управляемый lifecycle.
- [x] Критичные auth/permissions сценарии покрыты тестами.

### Sprint test / verification
- [x] Прогнан набор API/auth/permissions тестов спринта.
- [ ] Проверена совместимость frontend с обновлённым API-контрактом.
- [x] Результат теста и замечания зафиксированы ниже.

### Notes
- Статус: `in progress`
- Дата начала: `2026-04-04`
- Дата завершения:
- Итог теста: `pytest tests/auth/test_session_crud.py tests/auth/test_auth_api.py -q` -> 10 passed; `pytest tests/auth/test_auth_api.py -q` -> 8 passed; `pytest -m unit -q` -> 27 passed, 6 deselected
- Замечания:
  - Primary API base зафиксирован как `/api/v1`; для legacy-маршрутов оставлены совместимые alias на `/api` для переходного периода.
  - Единый источник API-префиксов: `app/api.py`; `app/main.py` собирает versioned и legacy router mounts из общих констант.
  - Session lifecycle усилен через `last_seen_at`, `revoked_at`, `revoked_reason`, `ip_address`, `last_seen_ip`; добавлена миграция `alembic/versions/20260404_01_auth_session_lifecycle.py`.
  - На логине включена rotation-стратегия: предыдущие сессии роли отзываются, выдаётся новый token; logout переводит сессию в revoked и затем чистит storage.
  - Cookie policy нормализована по окружениям в `app/auth/session_policy.py`; touch-семантика обновляет `last_seen_at` и audit-поля на активной сессии.
  - Общий error envelope для API-ошибок подключён через `app/api_errors.py`: новые ответы унифицированы, но сохраняют совместимость по полям `detail` и `error` для текущего frontend.
  - Optional CSRF strategy оформлена как double-submit cookie pattern: backend выставляет `csrf_token`, проверка включается только при `CSRF_ENABLED=true` и применяется к sensitive cookie-auth mutating endpoints (`consent`, `profile/update`, `auth logout/onboarding`).
  - Frontend contract дополнительно smoke-checked на patient/researcher sensitive flows: `consent`, `profile/update`, `onboarding`, `researcher logout`; в fetch-запросы добавлен `X-CSRF-Token` из cookie.
  - Полный фронтенд-аудит всех страниц и legacy-роутов остаётся отдельным хвостом спринта.

---

## Sprint 3. LLM/RAG Optimization + Bot Legacy Cleanup

Цель:
- улучшить производительность и диагностируемость LLM/RAG слоя;
- сократить мёртвый и compatibility-only код в bot-слое.

### 1. LLM / RAG optimization
- [x] Зафиксировать целевую схему pipeline: `classify -> build patient context -> retrieve knowledge -> assemble prompt -> call model -> persist/metrics`.
- [x] Разделить в коде и диагностике `patient context` и собственно `RAG retrieval`, чтобы не считать весь LLM-контекст "RAG".
- [x] Уменьшить количество broad `except` в LLM/RAG модулях, оставив graceful degradation только в явно согласованных точках.
- [x] Переиспользовать `httpx.AsyncClient` через lifecycle-managed схему для chat/oauth/embeddings вызовов.
- [x] Нормализовать timeout/retry/error handling по провайдеру и retrieval-слою.
- [x] Добавить более полезную диагностику: stage latency, provider errors, fallback points, prompt/context size, RAG hit/miss.
- [ ] Спроектировать и/или реализовать перенос embeddings search ближе к БД/`pgvector`.

### 2. Coverage for critical scenarios
- [ ] Добавить тесты на scheduler-safe behavior.
- [ ] Добавить тесты на routine flows.
- [ ] Добавить тесты на practice flows.
- [ ] Добавить тесты на profile endpoints.
- [ ] Добавить тесты на критичные LLM/RAG integration paths по согласованному минимуму.

### 3. Bot legacy cleanup
- [ ] Провести инвентаризацию bot entrypoints и import graph.
- [ ] Разделить bot-код на `active`, `compat-only`, `dead`.
- [ ] Удалить или изолировать неиспользуемый legacy-слой.
- [ ] Снизить лишние импортные связи между legacy и актуальным кодом.
- [ ] Обновить runbook/README по поддерживаемому bot path.

### Definition of done
- [ ] LLM/RAG слой стал предсказуемее по ошибкам и ресурсам.
- [ ] Формально зафиксировано, что текущая система — это `context-enriched assistant`, где RAG отвечает только за retrieval образовательных модулей.
- [ ] Критичные сценарии покрыты регрессией.
- [ ] Legacy-слой бота инвентаризирован и очищен.

### Sprint test / verification
- [ ] Прогнан набор LLM/RAG/bot/regression тестов спринта.
- [ ] Проверено, что cleanup не ломает поддерживаемый bot startup path.
- [ ] Результат теста и замечания зафиксированы ниже.

### Notes
- Статус: `in progress`
- Дата начала: `2026-04-04`
- Дата завершения:
- Итог теста:
- Замечания:
  - На старте спринта зафиксировано, что текущее ядро качества ответа определяется прежде всего `system prompt` + `patient context` + `chat history`, а не retrieval.
  - Текущий RAG в узком смысле ограничен поиском релевантных educational chunks; остальной LLM-контекст не должен трактоваться как RAG.
  - Главный порядок работ спринта: сначала наблюдаемость и явный pipeline, затем lifecycle-managed HTTP clients и error handling, затем migration плана/реализации для `pgvector`.
  - До миграции `pgvector` текущий retrieval остаётся дорогим: query embedding вычисляется сетевым вызовом, затем embeddings загружаются целиком и similarity считается в Python.
  - Отдельно проверить, какие деградации допустимы без ошибки для пользователя, а какие должны поднимать технический сигнал в логах/метриках.
  - В `app/llm/context_builder.py` введён `build_context_bundle()` с раздельной диагностикой по секциям контекста и retrieval.
  - В `app/llm/agent.py` добавлена pipeline-диагностика по стадиям `patient_context` / `parser` / `prompt` / `llm_call` без изменения пользовательского API-контракта чата.
  - Введён shared transport `app/llm/http.py`; `app/llm/pool.py`, `app/rag/retriever.py`, `app/rag/indexer.py` переведены на переиспользуемые `httpx.AsyncClient`, а API lifespan закрывает клиенты на shutdown.
  - В provider/retrieval слоях введены предметные ошибки `LLMTransportError` / `LLMResponseError` / `RetrievalError`; parser и agent переведены с broad `except` на более узкие категории для этих стадий.
  - Timeout/retry policy централизован в `app/llm/http.py` через `request_json_with_policy()`; oauth/chat/embeddings вызовы больше не дублируют вручную `httpx`-ошибки и retry-ветки в `pool/retriever/indexer`.
  - По состоянию на сейчас поиск `except Exception|except:` в `app/llm` и `app/rag` не находит broad handlers.
  - В `llm.llm_request_logs` добавлено поле `diagnostics_json` (миграция `alembic/versions/20260404_02_add_llm_request_diagnostics.py`) для сохранения полного pipeline trace по каждому LLM-turn.
  - `app/llm/agent.py` теперь сохраняет `classify/patient_context/parser/prompt/llm_call/summary` с явными `status`, `error_type`, `failure_stage`, `fallback_points`, размером prompt/context и RAG hit/miss.
  - `app/llm/context_builder.py` расширен полями `total_latency_ms`, `section_item_counts`, `rag.skipped_reason`, а также детализацией RAG latency на `embedding_request_ms`, `vector_search_ms`, `progress_lookup_ms`, чтобы было видно не только падение секции, но и точный bottleneck retrieval-пути.
  - Researcher chat logs теперь могут возвращать `diagnostics_json`, чтобы разбирать проблемные ответы без поиска по runtime-логам.
  - Для RAG добавлен readiness-слой `app/rag/capabilities.py`: retrieval теперь явно диагностирует backend (`python_cosine` vs `pgvector`) и причину fallback (`pgvector_extension_missing` / `embedding_vector_column_missing` / `embedding_vector_index_missing`).
  - `app/rag/retriever.py` уже умеет выбирать backend через capability-check и готов к SQL retrieval через `pgvector`.
  - Добавлена миграция `alembic/versions/20260404_03_add_pgvector_embedding_support.py`: при наличии server-side `vector` она создаёт `embedding_vector vector(1024)`, backfill из `embedding TEXT` и `ivfflat`-индекс; при отсутствии extension завершает ревизию безопасно через `NOTICE`.
  - `app/rag/indexer.py` переведён на dual write: если `embedding_vector` доступен, новые embeddings пишутся и в `embedding TEXT`, и в `embedding_vector`.
  - Server-side `pgvector` установлен локально вручную для PostgreSQL 17.5, extension `vector 0.8.1` успешно создан в `hemo_db`.
  - В `education.lesson_embeddings` локально создан `embedding_vector vector(1024)`, выполнен backfill `145/145` строк и создан `ivfflat`-индекс `ix_lesson_embeddings_embedding_vector_ivfflat`.
  - `app/rag/indexer.py` теперь логирует backend readiness перед переиндексацией, чтобы было видно, почему embeddings всё ещё пишутся только в JSON/TEXT слой.
  - Добавлен документ `LLM_upd_01.md` в корне проекта с отдельным планом по mixed anxiety/clinical policy и regression-защите.
  - Добавлены unit-тесты `tests/llm/test_context_builder.py`, `tests/llm/test_parser.py`, `tests/llm/test_http_policy.py`, `tests/llm/test_agent_diagnostics.py`, `tests/llm/test_rag_retriever.py`, `tests/llm/test_rag_indexer.py`; текущий локальный прогон: `pytest tests/llm/test_context_builder.py tests/llm/test_http_policy.py tests/llm/test_parser.py tests/llm/test_agent_diagnostics.py tests/llm/test_rag_retriever.py tests/llm/test_rag_indexer.py tests/llm/test_worker.py -q` -> 14 passed.

---

## Cross-sprint notes
Сюда можно добавлять краткие наблюдения, решения и договорённости, которые важны для следующих чатов.

- [ ] Зафиксированы архитектурные решения по config/bootstrap.
- [x] Зафиксированы архитектурные решения по config/bootstrap.
- [x] Зафиксированы правила маршрутизации API.
- [x] Зафиксирована auth/session policy.
- [ ] Зафиксирован подход к scheduler deployment.
- [x] Зафиксирован подход к scheduler deployment.
- [ ] Зафиксирован план по LLM/RAG migration.
- [x] Зафиксирован план по LLM/RAG migration.





