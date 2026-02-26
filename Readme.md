# GPT Support — Платформа поддержки пациентов на гемодиализе

Цифровая платформа для мониторинга состояния пациентов на программном гемодиализе.
Включает психометрические шкалы, трекинг витальных показателей,
рутинный мониторинг сна, управление распорядком дня, учёт медикаментов,
управление центрами и расписаниями диализа, образовательные модули,
панель исследователя и Telegram-бота.

---

## Стек технологий

| Слой                   | Технология                     |
| ---------------------- | ------------------------------ |
| **Backend**            | FastAPI (ASGI, uvicorn)        |
| **Telegram-бот**       | aiogram 3.4                    |
| **БД**                 | PostgreSQL (asyncpg)           |
| **ORM**                | SQLAlchemy 2.0 async           |
| **Миграции**           | Alembic                        |
| **Валидация**          | Pydantic 2.5                   |
| **Авторизация**        | Session-based + bcrypt         |
| **Frontend**           | HTML5 + Vanilla JS + CSS       |
| **Тесты**              | pytest + pytest-asyncio        |

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
- **PostgreSQL** — 10 схем: `users`, `scales`, `vitals`, `education`, `sleep`, `medications`, `kdqol`, `practices`, `routine`, `llm`
- **Alembic** — версионирование схемы БД
- **Frontend** — статические HTML/JS/CSS для пациента, исследователя и врача

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
│   │   ├── models.py             # ORM: User (+ is_onboarded)
│   │   ├── crud.py               # CRUD пользователей
│   │   ├── api.py                # API эндпоинты
│   │   └── schemas.py            # Pydantic-схемы
│   ├── scales/                   # Психометрические шкалы
│   │   ├── routers.py            # API: HADS, KOP-25A, PSQI, PSS-10, WCQ + KDQOL
│   │   ├── services.py           # Реестр конфигов, сохранение результатов
│   │   ├── registry.py           # Маппинг code -> calculator
│   │   ├── models.py             # ORM: ScaleResult, MeasurementPoint (KDQOL)
│   │   ├── config/               # Конфигурации опросников
│   │   │   ├── hads.py           # HADS: 14 вопросов
│   │   │   ├── kop_25a1.py       # КОП-25А1: 25 вопросов
│   │   │   ├── psqi.py           # PSQI: блоки вопросов о сне
│   │   │   ├── pss10.py          # PSS-10: 10 вопросов
│   │   │   └── wcq_lazarus.py    # WCQ (Лазарус): копинг-стратегии
│   │   ├── calculators/          # Калькуляторы баллов
│   │   │   ├── hads.py           # Тревога + Депрессия
│   │   │   ├── kop_25a1.py       # Приверженность лечению
│   │   │   ├── psqi.py           # 7 компонентов качества сна
│   │   │   ├── pss10.py          # Воспринимаемый стресс
│   │   │   ├── wcq_lazarus.py    # 8 субшкал совладания
│   │   │   └── kdqol.py          # Субшкалы KDQOL-SF 1.3
│   │   └── resources/
│   │       └── kdqol_sf_structure.json  # Структура вопросов KDQOL-SF
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
│   ├── practices/                # Самостоятельные практики (Блок C)
│   │   ├── router.py             # API: GET/POST практик и завершений
│   │   ├── models.py             # ORM: Practice, PracticeCompletion
│   │   └── schemas.py            # Pydantic-схемы
│   ├── medications/              # Медикаменты и назначения
│   │   ├── router.py             # API: назначения и приёмы
│   │   ├── service.py            # Бизнес-логика
│   │   ├── models.py             # ORM: MedicationPrescription, MedicationIntake
│   │   └── schemas.py            # Pydantic-схемы
│   ├── routine/                  # Распорядок дня (МКФ d230)
│   │   ├── router.py             # API: базовый шаблон, планы, верификация
│   │   ├── service.py            # Расчёт и логика планирования
│   │   ├── crud.py               # CRUD записей
│   │   ├── models.py             # ORM: BaselineRoutine, DailyPlan, DailyVerification
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
│   ├── llm/                      # LLM-слой: маршрутизация, ключевые слова, промпты
│   │   ├── router.py             # API endpoint для LLM-support
│   │   ├── service.py            # Бизнес-логика работы с LLM
│   │   ├── keywords.py           # Доменные ключевые слова и эвристики
│   │   └── prompts/              # Текстовые промпты по доменам
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
│   ├── notifications/            # Уведомления (Telegram)
│   ├── gpt_support/              # GPT-интеграция (заглушка)
│   └── core/                     # Конфигурация приложения
│       └── config.py
├── frontend/                     # Web-клиент
│   ├── patient/                  # Интерфейс пациента
│   │   ├── home.html             # Главная страница
│   │   ├── login.html            # Вход по номеру + PIN
│   │   ├── onboarding.html       # Онбординг новых пациентов
│   │   ├── profile.html          # Профиль
│   │   ├── vitals.html           # Ввод витальных
│   │   ├── education.html        # Обучение (урок + карточки)
│   │   ├── education_overview.html  # Навигатор обучения
│   │   ├── education_test.html   # Тесты к урокам
│   │   ├── scales_overview.html  # Сводка шкал
│   │   ├── hads.html             # Опросник HADS
│   │   ├── kop25a.html           # Опросник КОП-25А
│   │   ├── psqi.html             # Опросник PSQI
│   │   ├── pss10.html            # Шкала ШВС-10 (PSS-10)
│   │   ├── wcq_lazarus.html      # Опросник WCQ (Лазарус)
│   │   ├── kdqol.html            # Опросник KDQOL-SF 1.3
│   │   ├── consent.html          # Согласия
│   │   ├── sleep_tracker.html    # Рутинная оценка сна
│   │   ├── routine.html          # Распорядок дня (d230)
│   │   ├── medications.html      # Медикаменты
│   │   ├── practice.html         # Самостоятельные практики
│   │   ├── components/           # Переиспользуемые HTML-компоненты
│   │   │   ├── global_header.html
│   │   │   └── sidebar.html
│   │   ├── js/                   # JavaScript-модули
│   │   └── css/                  # Стили
│   ├── researcher/               # Интерфейс исследователя
│   │   ├── login.html            # Вход
│   │   ├── dashboard.html        # Панель управления
│   │   ├── centers.html          # Управление центрами диализа
│   │   ├── import_schedules.html # Импорт расписаний из CSV
│   │   ├── schedule_import_template.csv  # Шаблон CSV
│   │   ├── js/
│   │   └── css/
│   └── doctor/                   # Интерфейс врача
│       ├── dashboard.html        # Панель врача
│       ├── js/
│       └── css/
├── core/                         # Ядро (БД)
│   └── db/
│       ├── engine.py             # Async engine + session factory
│       ├── session.py            # Фабрика сессий
│       └── users.py              # Утилиты пользователей
├── scripts/                      # Утилиты и скрипты
│   ├── create_researcher.py      # Создание аккаунта исследователя
│   ├── create_test_patient.py    # Создание тестового пациента
│   ├── change_researcher_password.py  # Смена пароля исследователя
│   ├── import_lesson_from_md.py  # Импорт уроков из Markdown
│   ├── import_lesson_test_from_json.py  # Импорт тестов к урокам
│   ├── import_practices.py       # Импорт самостоятельных практик
│   ├── seed_education_lessons.py # Первичная загрузка уроков
│   ├── init_db_from_models.py    # Инициализация таблиц
│   └── ...                       # Диагностика, миграции
├── alembic/                      # Миграции БД
│   ├── env.py
│   └── versions/
├── content/                      # Образовательный контент (.md)
│   ├── education/
│   │   ├── psychology/           # Контент блока «Здоровый ум»
│   │   └── nephrology/           # Контент блока «Жизнь на диализе»
│   └── practice/
│       └── practices_block_a.md  # 9 самостоятельных практик
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
- Онбординг: флаг `is_onboarded` на модели User

### Психометрические шкалы (`app/scales/`)

**Реализованы:**

- **HADS** — Госпитальная шкала тревоги и депрессии (14 вопросов)
- **КОП-25А1** — Приверженность лечению (25 вопросов, 5 групп)
- **PSQI** — Питтсбургский опросник качества сна (7 компонентов + клинические флаги)
- **PSS-10 (ШВС-10)** — Шкала воспринимаемого стресса (10 вопросов)
- **WCQ Лазарус** — Способы совладающего поведения (8 субшкал, adaptive_ratio)
- **KDQOL-SF 1.3** — Качество жизни при болезни почек (точки измерения T0/T1/T2, CSV-экспорт)

Каждая шкала: `config/` (структура опросника) + `calculators/` (расчёт баллов) + API endpoints.

> Шкала **ТОБОЛ** удалена (миграция `20260225_01_remove_tobol_scale_results.py`).

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
- Блоки контента: `psychology` («Здоровый ум»), `nephrology` («Жизнь на диализе»)
- Импорт: `scripts/import_lesson_from_md.py`, `scripts/import_lesson_test_from_json.py`

### Самостоятельные практики (`app/practices/`)

- Независимые упражнения (Блок C): дыхательные, телесные, поведенческие
- Модели: `Practice`, `PracticeCompletion` (схема `practices`)
- Endpoints: `GET /api/practices`, `GET /api/practices/{id}`, `POST /api/practices/{id}/complete`
- Контент: `content/practice/practices_block_a.md` (9 практик)
- Импорт: `scripts/import_practices.py`

### Медикаменты (`app/medications/`)

- Назначения препаратов (`MedicationPrescription`): название, доза, схема приёма, статус
- Журнал фактических приёмов (`MedicationIntake`): слоты (morning/afternoon/evening), ретроспектива
- Схема БД: `medications`
- Поддержка самоназначения и врачебных назначений

### Распорядок дня / рутина (`app/routine/`)

- МКФ домен **d230**: мониторинг повседневных активностей
- Онбординг: базовый шаблон рутины (`BaselineRoutine`) с версионированием
- Ежедневный план (`DailyPlan`): шаблонные и кастомные активности
- Верификация выполнения (`DailyVerification`): оценка контроля дня
- Шаблоны для диализных и недиализных дней
- Схема БД: `routine`

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
- Активация точек измерения KDQOL (T0/T1/T2)
- CSV-экспорт результатов KDQOL

### Диализные центры и расписания (`app/dialysis/`)

- Справочник центров диализа (название, город, часовой пояс)
- Расписания диализа: привязка пациента к дням недели и сменам (утро/день/вечер)
- Soft-close паттерн: расписания не удаляются, а закрываются (аудит-трейл)
- CSV-импорт расписаний: двухшаговый процесс (preview → confirm)
- Сервис `is_dialysis_day()` — используется модулями vitals, sleep_tracker, routine
- Доступ: только для исследователей

### Рутинная оценка сна (`app/sleep_tracker/`)

- Ежедневный трекинг сна
- Метрики: TIB (Time In Bed), TST (Total Sleep Time), Sleep Efficiency (SE%)
- Нарушения сна: боль, зуд, ноктурия, СБН, тревога, шум
- Автоматическая привязка к дню диализа
- Защита от дубликатов (unique constraint: patient + date)
- API: POST/PUT/GET /sleep/me с пагинацией

### Telegram-бот (`app/bots/tg_bot/`)

- aiogram 3.x с FSM
- Inline-меню (/menu)
- Ввод витальных через бота (АД, пульс, вес)
- Обработчики: start, consent, questionnaire, vitals

### Страницы (`app/pages/`)

- Раздача HTML для пациента, исследователя и врача
- **Пациент:** `/patient/home`, `/patient/vitals`, `/patient/education`, `/patient/education_overview`, `/patient/education_test`, `/patient/scales`, `/patient/hads`, `/patient/kop25a`, `/patient/psqi`, `/patient/pss10`, `/patient/wcq_lazarus`, `/patient/kdqol`, `/patient/sleep_tracker`, `/patient/routine`, `/patient/medications`, `/patient/practice`, `/patient/profile`, `/patient/onboarding`
- **Исследователь:** `/researcher/dashboard`, `/researcher/centers`, `/researcher/import/schedules`

---

## База данных

PostgreSQL с разделением по схемам:

| Схема         | Назначение                                                         |
| ------------- | ------------------------------------------------------------------ |
| `users`       | Пользователи, согласия, аутентификация                             |
| `scales`      | Результаты прохождения шкал (ScaleResult)                          |
| `vitals`      | Измерения АД, пульса, веса, воды                                   |
| `education`   | Уроки, тесты, прогресс, практики к урокам                          |
| `sleep`       | Записи рутинной оценки сна (SleepRecord)                           |
| `medications` | Назначения и журнал приёмов медикаментов                           |
| `kdqol`       | Точки измерения и субшкальные оценки KDQOL-SF 1.3                  |
| `practices`   | Самостоятельные практики и факты выполнения                        |
| `routine`     | Базовые шаблоны, дневные планы и верификации рутины                |
| `llm`         | Конфигурация и данные LLM-подсистемы                               |
| `public`      | Служебные (alembic_version), центры диализа, расписания            |

### Ключевые связи

- `users.users.id` ← `scales.scale_results.user_id`
- `users.users.id` ← `vitals.bp_measurements.user_id` (и другие витальные)
- `users.users.id` ← `education.lesson_progress.user_id`
- `users.users.id` ← `sleep.sleep_records.patient_id`
- `users.users.id` ← `dialysis_schedules.patient_id`
- `users.users.id` ← `medications.medication_prescriptions.patient_id`
- `users.users.id` ← `routine.daily_plans.patient_id`
- `users.users.id` ← `practices.practice_completions.user_id`
- `users.users.center_id` → `centers.id`

---

## Frontend

### Интерфейс пациента (`frontend/patient/`)

- Вход по номеру пациента + PIN
- Онбординг при первом входе (`is_onboarded`)
- Главная страница с навигацией
- Ввод витальных показателей с графиками
- Прохождение психометрических шкал
- Обучающие материалы (карточки) с тестами
- Самостоятельные практики (дыхательные, телесные, поведенческие)
- Рутинная оценка сна
- Распорядок дня: планер + вечерняя верификация
- Учёт медикаментов: назначения и журнал приёмов
- Профиль с агрегированной сводкой

### Интерфейс исследователя (`frontend/researcher/`)

- Вход по логину/паролю
- Панель управления пациентами
- Создание новых пациентов, сброс PIN
- Управление центрами диализа
- Импорт расписаний из CSV (3-шаговый процесс: загрузка → preview → применение)
- Активация точек измерения KDQOL и CSV-экспорт результатов

### Интерфейс врача (`frontend/doctor/`)

- Панель мониторинга (в разработке)

---

## Импорт контента

```bash
# Уроки psychology (с очисткой)
d:/PROJECT/venv/venv311/.venv/Scripts/python scripts/import_lesson_from_md.py \
  --block psychology --clear --dir content/education/psychology

# Тесты psychology
d:/PROJECT/venv/venv311/.venv/Scripts/python scripts/import_lesson_test_from_json.py \
  --block psychology --dir content/education/psychology

# Уроки nephrology
d:/PROJECT/venv/venv311/.venv/Scripts/python scripts/import_lesson_from_md.py \
  --block nephrology --dir content/education/nephrology

# Тесты nephrology
d:/PROJECT/venv/venv311/.venv/Scripts/python scripts/import_lesson_test_from_json.py \
  --block nephrology --dir content/education/nephrology

# Самостоятельные практики
python scripts/import_practices.py
# → добавлено 9 / обновлено 0 / ошибок 0
```

---

## Запуск

```bash
# API (основное приложение)
uvicorn app.main:app --reload

# Telegram-бот
python -m app.bots.tg_bot.main

# Смена пароля исследователя
python scripts/change_researcher_password.py
# (следовать инструкциям)

# Тесты
pytest
```

---

## Roadmap (в разработке)

- **RAG-система** — персонализация диалогов GPT по данным пациента
- **GPT Health Support Agents:**
  - Coordinator Agent — управление потоками
  - RAG Agent — ответы с учётом данных (scales, vitals)
  - Motivator Agent — поддержка и напоминания
  - Education Agent — обучающие сценарии
- **Уведомления** — напоминания об обучении, практиках, витальных
- **Панель врача** — расширенный мониторинг
- **Rehab Metrics (МКФ)** — оценка динамики по доменам

---

## Реабилитационные домены (МКФ)

Проект ориентирован на оценку динамики по доменам МКФ:

- b130 Энергия и мотивация
- b152 Эмоциональные функции
- b164 Когнитивные функции
- **d230 Выполнение повседневных задач** ← реализован модуль `routine`
- d570 Самообслуживание
- d760 Межличностные отношения
