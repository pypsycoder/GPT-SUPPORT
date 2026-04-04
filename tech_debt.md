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
- [ ] Уменьшить количество broad `except` в LLM/RAG модулях.
- [ ] Переиспользовать `httpx.AsyncClient` через lifecycle-managed схему.
- [ ] Нормализовать timeout/retry/error handling.
- [ ] Спроектировать и/или реализовать перенос embeddings search ближе к БД/`pgvector`.
- [ ] Добавить более полезную диагностику: latency, provider errors, fallback points.

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
- [ ] Критичные сценарии покрыты регрессией.
- [ ] Legacy-слой бота инвентаризирован и очищен.

### Sprint test / verification
- [ ] Прогнан набор LLM/RAG/bot/regression тестов спринта.
- [ ] Проверено, что cleanup не ломает поддерживаемый bot startup path.
- [ ] Результат теста и замечания зафиксированы ниже.

### Notes
- Статус: `not started`
- Дата начала:
- Дата завершения:
- Итог теста:
- Замечания:

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





