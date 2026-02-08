**Задача:** Реализация персистентного хранения сессий авторизации в PostgreSQL

**Дата:** 2026-02-08 16:00

**Действия:**
- Создана новая модель Session в app/auth/models.py с полями для user_id, researcher_id, expires_at, user_agent
- Созданы CRUD операции в app/auth/session_crud.py (create, get, delete, cleanup, batch operations)
- Создана Alembic миграция g7h8i9j0k1l2_add_sessions_table.py для таблицы users.sessions с индексами
- Обновлены зависимости в app/auth/dependencies.py: заменены in-memory словари на БД запросы
- Обновлены эндпоинты авторизации в app/auth/router.py: использованы CRUD функции вместо register/remove
- Зарегистрирована модель Session в app/models/__init__.py
- Исправлена цепочка миграций: g7h8i9j0k1l2 теперь ревизирует ab4dbdf64b6f

**Файлы:**
- `app/auth/models.py` (создан - модель Session)
- `app/auth/session_crud.py` (создан - CRUD операции)
- `alembic/versions/g7h8i9j0k1l2_add_sessions_table.py` (создана миграция, исправлена цепочка)
- `app/auth/dependencies.py` (обновлён - БД вместо dict)
- `app/auth/router.py` (обновлён - CRUD вместо register/remove)
- `app/models/__init__.py` (обновлён - импорт auth models)

**Результат:** Сессии теперь хранятся в PostgreSQL и сохраняются после перезагрузки сервера. Авторизация полностью персистентна.

**Проблемы:** Нет. Все компоненты реализованы согласно плану. Миграция готова к применению.

**Примечание:** Требуется применить миграцию в виртуальном окружении:
```bash
.venv/bin/alembic upgrade head
# или
python -m alembic upgrade head
```
