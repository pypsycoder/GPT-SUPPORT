# AGENTS.md — GPT Health Support

Точка входа для кодинг-агентов (Codex, Cursor и т.п.). Полная спецификация —
в [`CLAUDE.md`](CLAUDE.md); этот файл — краткая выжимка обязательных правил.

## Что это

Цифровая платформа поддержки пациентов на программном гемодиализе:
психообразование, трекинг, самоменеджмент, сбор данных для исследователя.
**Не система лечения.** Медицинских решений не принимает.

## Стек

FastAPI (async) · PostgreSQL + asyncpg · SQLAlchemy 2.0 async · Alembic ·
Pydantic 2 · session-based auth + bcrypt · frontend — vanilla HTML/CSS/JS ·
pytest + pytest-asyncio.

## Обязательные правила

1. **Архитектура модуля** — `models.py` / `schemas.py` / `crud.py` / `service.py`
   / `router.py`. Слои не смешивать: бизнес-логика только в `service.py`,
   `commit()` только в `router.py`. Эталон — `app/vitals/`.
2. **Alembic** — миграции не генерировать и не применять без явной команды.
   Порядок запуска, верификация revision, правила `stamp` — в
   [`ALEMBIC_RUNBOOK.md`](ALEMBIC_RUNBOOK.md).
3. **Схемы БД** (`__table_args__` schema) — не менять без уточнения.
4. **Не удалять расписания диализа** — soft-close (закрытие, не удаление).
5. **`gpt_support/`** — заглушка, не трогать без явной задачи.
6. **git** — не коммитить и не пушить без явной команды пользователя; если не на
   `master`, сначала ветка. Сообщения коммитов заканчивать строкой
   `Co-Authored-By: …` согласно настройке инструмента.

## Документация

- **`ROADMAP_AGENT.md` — основной документ** по агентскому / LLM-контуру.
  Прогресс фиксировать правкой секции в нём, **не новым файлом**.
- **Не создавать новые корневые `.md`.** Развёрнутый отчёт, если нужен отдельным
  файлом, — в `docs/agent/` + ссылка в `ROADMAP_AGENT.md` («Связанные документы»).
- Допустимые корневые `.md`: `Readme.md`, `CLAUDE.md`, `AGENTS.md`,
  `ROADMAP_AGENT.md`, `ALEMBIC_RUNBOOK.md`, `SPRINT1_INVESTIGATIONS.md`.

## Окружение и запуск

```bash
# venv (на dev-машине есть):
d:/PROJECT/venv/venv311/.venv/Scripts/python -m pytest      # тесты
d:/PROJECT/venv/venv311/.venv/Scripts/python -m uvicorn app.main:app --reload
```

Windows: в bash-инструменте `rm`, не `del`.

## С чего начать новую задачу

Уточнить: (1) в каком модуле работаем; (2) нужна ли Alembic-миграция;
(3) новый модуль или расширение существующего. Держаться паттернов `app/vitals/`.
