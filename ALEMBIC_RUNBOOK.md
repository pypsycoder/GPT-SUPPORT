# Alembic Runbook

Дата: `2026-04-04`

Короткий runbook для безопасной работы с миграциями в этом проекте.

## Главные правила

1. Не запускать Alembic-команды параллельно.
2. Источник правды по текущей ревизии:
   - сначала `public.alembic_version`,
   - потом уже `alembic current`.
3. После любой нетривиальной миграции проверять не только revision, но и фактическую схему.
4. `stamp` использовать только если схема уже вручную приведена в нужное состояние.

## Безопасный порядок команд

### Проверить текущее состояние

```bat
alembic current
```

И отдельно:

```sql
SELECT version_num FROM public.alembic_version;
```

Если выводы не совпадают, не делать следующий шаг вслепую. Сначала проверить:
- не была ли параллельно запущена другая Alembic-команда;
- завершилась ли предыдущая команда полностью;
- соответствует ли фактическая схема ожидаемой ревизии.

### Применить миграции

```bat
alembic upgrade head
```

или точечно:

```bat
alembic upgrade <revision>
```

После этого дождаться завершения команды и только потом выполнять:

```bat
alembic current
```

### Откатить миграцию

```bat
alembic downgrade <revision>
```

После этого проверить:

```sql
SELECT version_num FROM public.alembic_version;
```

и фактическое состояние таблиц / колонок / индексов.

## Когда можно использовать `stamp`

`stamp` допустим только в одном случае:
- схема уже вручную синхронизирована с нужной ревизией,
- и нужно только выровнять `alembic_version`.

Пример:
- колонка уже создана вручную;
- backfill уже выполнен вручную;
- индекс уже создан вручную;
- только после этого:

```bat
alembic stamp <revision>
```

Нельзя использовать `stamp` как замену `upgrade`, если DDL ещё не применён.

## Что проверять после миграции

Минимальный набор:

1. Ревизия:

```sql
SELECT version_num FROM public.alembic_version;
```

2. Колонки:

```sql
SELECT column_name, udt_name
FROM information_schema.columns
WHERE table_schema = '<schema>'
  AND table_name = '<table>';
```

3. Индексы:

```sql
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = '<schema>'
  AND tablename = '<table>';
```

4. Для backfill:

```sql
SELECT COUNT(*) AS total, COUNT(<column>) AS filled
FROM <schema>.<table>;
```

## Что делать, если `alembic current` выглядит подозрительно

1. Не запускать сразу ещё одну Alembic-команду.
2. Проверить:

```sql
SELECT version_num FROM public.alembic_version;
```

3. Проверить фактическую схему.
4. Если БД уже в нужном состоянии, а revision не совпадает:
   использовать `alembic stamp <revision>` только после ручной верификации.

## Практический урок из текущего кейса

Проблема с `20260404_03` оказалась не в "сломанном Alembic", а в гонке команд:
- `upgrade/stamp/current` запускались слишком близко друг к другу;
- `current` успевал показать старое состояние;
- это выглядело как рассинхрон, хотя `public.alembic_version` уже был обновлён.

Вывод:
- Alembic в этом проекте нужно запускать строго последовательно;
- для спорных ситуаций первичный источник правды — сама БД, а не CLI-вывод.
