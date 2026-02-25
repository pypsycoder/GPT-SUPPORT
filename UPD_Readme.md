# GPT Support — Платформа поддержки пациентов на гемодиализе

Цифровая платформа для мониторинга состояния пациентов на программном гемодиализе.
Включает психометрические шкалы, трекинг витальных показателей,
рутинный мониторинг сна, управление центрами и расписаниями диализа,
образовательные модули, панель исследователя и Telegram-бота.

---

## Стек технологий


| Слой                   | Технология     |
| ---------------------------- | -------------------------- |
| **Backend**                | FastAPI (ASGI, uvicorn)  |
| **Telegram-бот**        | aiogram 3.4              |
| **БД**                   | PostgreSQL (asyncpg)     |
| **ORM**                    | SQLAlchemy 2.0 async     |
| **Миграции**       | Alembic                  |
| **Валидация**     | Pydantic 2.5             |
| **Авторизация** | Session-based + bcrypt   |
| **Frontend**               | HTML5 + Vanilla JS + CSS |
| **Тесты**             | pytest + pytest-asyncio  |

---

## Быстрый старт

```bash
# 1. Установка зависимостей
pip install -r requirements.txt

# 2. Настройка .env
cp .env.example .env
# Заполнить: DATABASE_URL, BOT_TOKEN

# 3. Миграции
alembic upgrade head

# 4. Запуск API
uvicorn app.main:app --reload

# 5. Запуск Telegram-бота (отдельно)
python -m app.bots.tg_bot.main
```

---

## Архитектура

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  Frontend   │────▶│  FastAPI API  │────▶│ PostgreSQL  │
│ (HTML/JS)   │     │  (uvicorn)   │     │ (asyncpg)   │
└─────────────┘     └──────────────┘     └─────────────┘
                          ▲
┌─────────────┐           │
│ Telegram Bot│───────────┘
│ (aiogram)   │
└─────────────┘
```

- **FastAPI** — REST API для всех модулей
- **aiogram** — Telegram-бот с FSM для ввода витальных
- **PostgreSQL** — 5 схем: `users`, `scales`, `vitals`, `education`, `sleep` + таблицы в `public`
- **Alembic** — версионирование схемы БД
- **Frontend** — статические HTML/JS/CSS для пациента и исследователя

---

## Дерево каталогов (актуальное)

```
.
├── app/                          # Backend (FastAPI)
│   ├── main.py                   # Точка входа, регистрация роутеров
│   ├── models/                   # Общий declarative Base
│   ├── auth/                     # Авторизация (session, PIN, пароли)
│   │   ├── router.py             # Login/logout эндпоинты
│   │   ├── service.py            # Бизнес-логика аутентификации
│   │   ├── security.py           # bcrypt, токены
│   │   ├── session_crud.py       # CRUD сессий
│   │   ├── dependencies.py       # FastAPI Depends (get_current_user)
│   │   ├── models.py             # ORM: Session
│   │   └── schemas.py            # Pydantic-схемы
│   ├── users/                    # Пользователи (пациенты)
│   │   ├── models.py             # ORM: User
│   │   ├── crud.py               # CRUD пользователей
│   │   ├── api.py                # API эндпоинты
│   │   └── schemas.py            # Pydantic-схемы
│   ├── scales/                   # Психометрические шкалы
│   │   ├── routers.py            # API: GET/POST для HADS, TOBOL, KOP-25A, PSQI
│   │   ├── services.py           # Реестр конфигов, сохранение результатов
│   │   ├── registry.py           # Маппинг code -> calculator
│   │   ├── models.py             # ORM: ScaleResult
│   │   ├── config/               # Конфигурации опросников
│   │   │   ├── hads.py           # HADS: 14 вопросов
│   │   │   ├── kop_25a1.py       # КОП-25А1: 25 вопросов
│   │   │   ├── psqi.py           # PSQI: блоки вопросов о сне
│   │   │   └── tobol.py          # ТОБОЛ: парсинг из .md
│   │   └── calculators/          # Калькуляторы баллов
│   │       ├── hads.py           # Тревога + Депрессия
│   │       ├── kop_25a1.py       # Приверженность лечению
│   │       ├── psqi.py           # 7 компонентов качества сна
│   │       └── tobol.py          # 12 профилей отношения к болезни
│   ├── vitals/                   # Витальные показатели
│   │   ├── router.py             # API: АД, пульс, вес, вода
│   │   ├── service.py            # Валидация и подготовка данных
│   │   ├── crud.py               # Генерик-CRUD
│   │   ├── models.py             # ORM: BP, Pulse, Weight, Water
│   │   └── schemas.py            # Pydantic-схемы
│   ├── education/                # Обучающие материалы
│   │   ├── router.py             # API уроков и тестов
│   │   ├── service.py            # Сервисный слой
│   │   ├── import_md.py          # Импорт из Markdown
│   │   ├── models.py             # ORM: Lesson, LessonCard, LessonTest
│   │   └── schemas.py            # Pydantic-схемы
│   ├── dialysis/                 # Центры и расписания диализа
│   │   ├── router.py             # API: центры, расписания, CSV-импорт
│   │   ├── service.py            # is_dialysis_day() — определение дня диализа
│   │   ├── crud.py               # CRUD центров и расписаний
│   │   ├── csv_import.py         # Парсинг CSV и preview-подтверждение
│   │   ├── models.py             # ORM: Center, DialysisSchedule
│   │   └── schemas.py            # Pydantic-схемы + импорт
│   ├── sleep_tracker/            # Рутинная оценка сна
│   │   ├── router.py             # API: /sleep/me (CRUD)
│   │   ├── service.py            # TIB, SE%, late_entry, dialysis_day
│   │   ├── crud.py               # CRUD записей сна
│   │   ├── models.py             # ORM: SleepRecord (схема sleep)
│   │   └── schemas.py            # Pydantic + enums качества сна
│   ├── consent/                  # Согласия пациента
│   │   ├── router.py             # GET/POST согласий
│   │   ├── service.py            # Бизнес-логика
│   │   └── schemas.py            # Pydantic-схемы
│   ├── profile/                  # Профиль пациента
│   │   ├── router.py             # API профиля
│   │   ├── service.py            # Агрегатор данных (витальные + шкалы + обучение)
│   │   └── schemas.py            # Pydantic-схемы
│   ├── researchers/              # Панель исследователя
│   │   ├── router.py             # API панели
│   │   ├── crud.py               # Создание пациентов, сброс PIN
│   │   ├── models.py             # ORM: Researcher
│   │   └── schemas.py            # Pydantic-схемы
│   ├── pages/                    # Раздача HTML-страниц
│   │   └── router.py             # Маршруты /patient/... и /researcher/...
│   ├── bots/                     # Telegram-бот
│   │   └── tg_bot/
│   │       ├── main.py           # Инициализация Bot + Dispatcher
│   │       ├── handlers/         # Обработчики (start, consent, vitals)
│   │       ├── keyboards/        # Inline/reply клавиатуры
│   │       ├── routers/          # Роутеры (меню, пользователь)
│   │       └── middlewares/      # DB middleware
│   ├── notifications/            # Уведомления (заглушка)
│   ├── gpt_support/              # GPT-интеграция (заглушка)
│   └── core/                     # Конфигурация приложения
│       └── config.py
├── frontend/                     # Web-клиент
│   ├── patient/                  # Интерфейс пациента
│   │   ├── home.html             # Главная страница
│   │   ├── login.html            # Вход по номеру + PIN
│   │   ├── profile.html          # Профиль
│   │   ├── vitals.html           # Ввод витальных
│   │   ├── education.html        # Обучение
│   │   ├── scales_overview.html  # Сводка шкал
│   │   ├── hads.html             # Опросник HADS
│   │   ├── kop25a.html           # Опросник КОП-25А
│   │   ├── tobol.html            # Опросник ТОБОЛ
│   │   ├── psqi.html             # Опросник PSQI
│   │   ├── consent.html          # Согласия
│   │   ├── sleep_tracker.html    # Рутинная оценка сна
│   │   ├── js/                   # JavaScript-модули
│   │   └── css/                  # Стили
│   ├── researcher/               # Интерфейс исследователя
│   │   ├── login.html            # Вход
│   │   ├── dashboard.html        # Панель управления
│   │   ├── centers.html          # Управление центрами диализа
│   │   └── import_schedules.html # Импорт расписаний из CSV
│   └── doctor/                   # Интерфейс врача (прототип)
├── core/                         # Ядро (БД)
│   └── db/
│       ├── engine.py             # Async engine + session factory
│       ├── session.py            # Фабрика сессий
│       └── users.py              # Утилиты пользователей
├── scripts/                      # Утилиты и скрипты
│   ├── create_researcher.py      # Создание аккаунта исследователя
│   ├── create_test_patient.py    # Создание тестового пациента
│   ├── seed_education_lessons.py # Загрузка уроков
│   ├── import_lesson_test_from_json.py  # Импорт тестов
│   ├── init_db_from_models.py    # Инициализация таблиц
│   └── ...                       # Диагностика, миграции
├── alembic/                      # Миграции БД
│   ├── env.py
│   └── versions/
├── tests/                        # Тесты
│   ├── conftest.py
│   ├── test_migrations.py
│   ├── bot/                      # Тесты бота
│   └── vitals/                   # Тесты витальных
├── content/                      # Образовательный контент (.md)
├── agents/                       # AI-агенты (заглушка)
├── config.py                     # Корневой конфиг (.env)
├── requirements.txt              # Зависимости Python
├── alembic.ini                   # Конфигурация Alembic
└── pytest.ini                    # Конфигурация pytest
```

---

## Модули

### Авторизация (`app/auth/`)

- **Пациенты**: вход по номеру + 4-значный PIN
- **Исследователи**: вход по логину + пароль
- Session-based аутентификация через cookie
- Блокировка после 7 неудачных попыток PIN
- bcrypt-хэширование, генерация session token

### Пользователи (`app/users/`)

- ORM-модель User (схема `users`)
- Поиск по telegram_id, patient_number
- Управление согласиями и профилем

### Психометрические шкалы (`app/scales/`)

**Реализованы:**

- **HADS** — Госпитальная шкала тревоги и депрессии (14 вопросов)
- **ТОБОЛ** — Тип отношения к болезни (12 профилей)
- **КОП-25А1** — Приверженность лечению (25 вопросов, 5 групп)
- **PSQI** — Питтсбургский опросник качества сна (7 компонентов + клинические флаги)

Каждая шкала: `config/` (структура опросника) + `calculators/` (расчёт баллов) + API endpoints.

### Витальные показатели (`app/vitals/`)

- Артериальное давление (систолическое/диастолическое)
- Пульс (уд/мин)
- Вес (кг)
- Водный баланс (мл)
- Контекст измерения (до/после диализа, утро, вечер)
- API: CRUD + /me-эндпоинты для текущего пользователя

### Обучение (`app/education/`)

- Уроки (Lesson) с карточками (LessonCard) из Markdown
- Тесты (LessonTest) с вопросами (LessonTestQuestion)
- Прогресс прохождения (LessonProgress, LessonTestResult)
- Практики (PracticeLog)
- Темы: психология, нефрология

### Согласия (`app/consent/`)

- Управление согласиями на обработку ПДн
- GET — текущий статус, POST — принятие

### Профиль пациента (`app/profile/`)

- Агрегация данных: витальные + шкалы + обучение
- Обновление ФИО, возраста, пола

### Панель исследователя (`app/researchers/`)

- Создание пациентов с автогенерацией номера и PIN
- Сброс PIN
- Просмотр списка пациентов и их данных
- Управление центрами диализа
- Назначение расписаний диализа пациентам
- Импорт расписаний из CSV (preview → подтверждение → применение)

### Диализные центры и расписания (`app/dialysis/`)

- Справочник центров диализа (название, город, часовой пояс)
- Расписания диализа: привязка пациента к дням недели и сменам (утро/день/вечер)
- Soft-close паттерн: расписания не удаляются, а закрываются (аудит-трейл)
- CSV-импорт расписаний: двухшаговый процесс (preview → confirm) с разрешением конфликтов
- Сервис `is_dialysis_day()` — используется другими модулями (vitals, sleep_tracker)
- API: CRUD центров, создание/замена расписаний, импорт
- Доступ: только для исследователей

### Рутинная оценка сна (`app/sleep_tracker/`)

- Ежедневный трекинг сна (или 3–4 раза в неделю)
- Метрики: время засыпания/пробуждения, TIB (Time In Bed), TST (Total Sleep Time)
- Расчёт Sleep Efficiency (SE% = TST/TIB × 100)
- Качество сна: ночные пробуждения, латенция засыпания, утреннее самочувствие
- Нарушения сна: боль, зуд, ноктурия, СБН, тревога, шум
- Автоматическая привязка к дню диализа через `is_dialysis_day()`
- Защита от дубликатов (unique constraint: patient + date)
- Отслеживание поздних записей (после 14:00) и ретроспективных записей
- API: POST/PUT/GET /sleep/me с пагинацией

### Telegram-бот (`app/bots/tg_bot/`)

- aiogram 3.x с FSM
- Inline-меню (/menu)
- Ввод витальных через бота (АД, пульс, вес)
- Обработчики: start, consent, questionnaire, vitals

### Страницы (`app/pages/`)

- Раздача HTML для пациента и исследователя
- Session-based маршруты: `/patient/...`, `/researcher/...`
- Новые маршруты: `/patient/sleep_tracker`, `/researcher/centers`, `/researcher/import/schedules`
- Legacy-маршруты: `/p/{token}/...` (обратная совместимость)

---

## База данных

PostgreSQL с разделением по схемам:


| Схема  | Назначение                                                                    |
| ------------- | ----------------------------------------------------------------------------------------- |
| `users`     | Пользователи, согласия, аутентификация                |
| `scales`    | Результаты прохождения шкал (ScaleResult)                      |
| `vitals`    | Измерения АД, пульса, веса, воды                               |
| `education` | Уроки, тесты, прогресс, практики                              |
| `sleep`     | Записи рутинной оценки сна (SleepRecord)                         |
| `public`    | Служебные (alembic_version), центры диализа, расписания |

### Ключевые связи

- `users.users.id` <- `scales.scale_results.user_id`
- `users.users.id` <- `vitals.bp_measurements.user_id` (и другие витальные)
- `users.users.id` <- `education.lesson_progress.user_id`
- `users.users.id` <- `sleep.sleep_records.patient_id`
- `users.users.id` <- `dialysis_schedules.patient_id`
- `users.users.center_id` -> `centers.id`

---

## Frontend

### Интерфейс пациента (`frontend/patient/`)

- Вход по номеру пациента + PIN
- Главная страница с навигацией
- Ввод витальных показателей с графиками
- Прохождение психометрических шкал
- Обучающие материалы (карточки)
- Рутинная оценка сна (выбор ночи, 7 вопросов, детекция дубликатов)
- Профиль с агрегированной сводкой

### Интерфейс исследователя (`frontend/researcher/`)

- Вход по логину/паролю
- Панель управления пациентами
- Создание новых пациентов, сброс PIN
- Управление центрами диализа
- Импорт расписаний из CSV (3-шаговый процесс: загрузка → preview → применение)

---

## Roadmap (в разработке)

- **RAG-система** — персонализация диалогов GPT по данным пациента
- **GPT Health Support Agents:**
  - Coordinator Agent — управление потоками
  - RAG Agent — ответы с учётом данных (scales, vitals)
  - Motivator Agent — поддержка и напоминания
  - Education Agent — обучающие сценарии
- **Rehab Metrics (МКФ)** — оценка динамики по доменам
- **Уведомления** — напоминания об обучении, практиках, витальных
- **Панель врача** — расширенный мониторинг

---

## Реабилитационные домены (МКФ)

Проект ориентирован на оценку динамики по доменам МКФ:

- b130 Энергия и мотивация
- b152 Эмоциональные функции
- b164 Когнитивные функции
- d230 Выполнение повседневных задач
- d570 Самообслуживание
- d760 Межличностные отношения

---

## Запуск

```bash
# API (основное приложение)
uvicorn app.main:app --reload

# Telegram-бот
python -m app.bots.tg_bot.main

# Смена пароля исследователя
python .\scripts\change_researcher_password.py
дальше следовать инструкциям

# Тесты
pytest
```
