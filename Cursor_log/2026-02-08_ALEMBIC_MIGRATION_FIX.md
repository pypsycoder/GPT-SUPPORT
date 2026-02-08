**Задача:** Исправить дублирование логов Alembic и конфликт миграций

**Дата:** 2026-02-08

**Действия:**
- Исправлен конфликт múltiple heads в цепочке миграций
- Переназначен родитель для `d2f20e5011be_merge_multiple_heads.py` с двух ветвей на одну (`c9f0e1d2a3b4`)
- Повышен уровень логирования с INFO на WARN в `alembic.ini` для уменьшения дублирования
- Добавлен флаг `disable_existing_loggers=False` в `alembic/env.py`
- Создан скрипт проверки миграционных голов (`scripts/check_heads.py`)

**Файлы:**
- `alembic/versions/d2f20e5011be_merge_multiple_heads.py` (изменён: `down_revision`)
- `alembic.ini` (изменён: `level = INFO` → `level = WARN` для alembic логгера)
- `alembic/env.py` (изменён: добавлен `disable_existing_loggers=False`)
- `scripts/check_heads.py` (создан)

**Результат:** Единая цепь миграций (a515d149cfa3 → ... → d2f20e5011be). Дублирование логов должно быть уменьшено.

**Проблемы:** Требуется протестировать `alembic upgrade heads` в терминале после этих изменений
