# CLAUDE.md — GPT Health Support

## Контекст проекта

Цифровая платформа поддержки пациентов на программном гемодиализе.
**Важно:** это НЕ система лечения. Платформа обеспечивает психообразование, трекинг,
поддержку самоменеджмента и сбор данных для исследователя. Медицинских решений не принимает.

---

## Стек

| Слой | Технология |
|---|---|
| Backend | FastAPI (ASGI, uvicorn) |
| Telegram-бот | aiogram 3.4 |
| БД | PostgreSQL (asyncpg) |
| ORM | SQLAlchemy 2.0 async |
| Миграции | Alembic |
| Валидация | Pydantic 2.5 |
| Авторизация | Session-based + bcrypt |
| Frontend | HTML5 + Vanilla JS + CSS |
| Тесты | pytest + pytest-asyncio |

---

## Архитектура модулей

Каждый модуль в `app/` строго следует структуре:

```
app/<module>/
    models.py    # SQLAlchemy ORM модели
    schemas.py   # Pydantic схемы (Create, Update, Read, CreateMe)
    crud.py      # CRUD-слой (только работа с БД, без бизнес-логики)
    service.py   # Бизнес-логика: валидация, подготовка данных
    router.py    # FastAPI эндпоинты
```

**Правило:** не смешивать слои. Бизнес-логика — только в service.py, не в router.py и не в crud.py.

---

## Паттерны кода

### Models (SQLAlchemy 2.0 async)

```python
from __future__ import annotations
from uuid import uuid4
from sqlalchemy import Column, DateTime, Integer, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declared_attr
from app.models import Base

class SomeBase(Base):
    __abstract__ = True

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id = Column(Integer, ForeignKey("users.users.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    @declared_attr
    def __table_args__(cls):
        return (
            Index(f"ix_{cls.__tablename__}_user_id", "user_id"),
            {"schema": "schema_name"},  # всегда указываем схему
        )
```

- UUID как primary key (uuid4)
- ForeignKey всегда с полным путём: `"users.users.id"`
- Схема БД указывается в `__table_args__`
- `created_at` / `updated_at` — обязательны

### Schemas (Pydantic 2.5)

```python
from pydantic import BaseModel, ConfigDict

class SomeBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    field: str

class SomeCreate(SomeBase):       # для POST (с user_id)
    pass

class SomeCreateMe(BaseModel):    # для POST /me (user_id из сессии)
    field: str
    # без user_id — он берётся из Depends(get_current_user)

class SomeUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    field: Optional[str] = None   # все поля Optional

class SomeRead(SomeBase):         # для ответов
    id: UUID
    created_at: datetime
    updated_at: datetime
```

- `CreateMe` схемы не содержат `user_id` — он всегда из сессии
- `Update` схемы — все поля Optional
- `Read` схемы наследуют от Base + добавляют id/timestamps

### CRUD

```python
# Генерик-паттерн как в vitals/crud.py
class SomeCRUD(Generic[ModelType, CreateSchemaType, UpdateSchemaType]):
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def create(self, session: AsyncSession, obj_in: CreateSchemaType) -> ModelType:
        data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_none=True)
        db_obj = self.model(**data)
        session.add(db_obj)
        await session.flush()
        await session.refresh(db_obj)
        return db_obj

# Инстанс создаётся в конце файла:
some_crud = SomeCRUD(SomeModel)
```

- `flush()` + `refresh()` после create — не `commit()` (коммит в router)
- `commit()` всегда в router, не в crud и не в service
- `exclude_none=True` в `model_dump()`

### Service

```python
class SomeService:
    @staticmethod
    def validate_field(value: int) -> None:
        if not MIN <= value <= MAX:
            raise ValueError("Сообщение об ошибке")

    @classmethod
    def prepare_data(cls, *, user_id: int, field: str, ...) -> SomeCreate:
        cls.validate_field(field)
        return SomeCreate(user_id=user_id, field=field, ...)
```

- Только статические методы / classmethod
- Валидация перед возвратом схемы
- `measured_at` нормализуется в UTC через `normalize_measured_at()`

### Router

```python
router = APIRouter(prefix="/module", tags=["module"])

# Публичный эндпоинт (без авторизации)
@router.post("/items", response_model=schemas.SomeRead)
async def create_item(
    payload: schemas.SomeCreate,
    session: AsyncSession = Depends(get_session),
):
    prepared = service.SomeService.prepare_data(**payload.model_dump())
    item = await crud.some_crud.create(session, prepared)
    await session.commit()
    return item

# /me эндпоинт (авторизованный пользователь)
@router.post("/items/me", response_model=schemas.SomeRead)
async def create_item_me(
    payload: schemas.SomeCreateMe,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_async_session),
):
    prepared = service.SomeService.prepare_data(user_id=user.id, **payload.model_dump())
    item = await crud.some_crud.create(session, prepared)
    await session.commit()
    await session.refresh(item)
    return item
```

- Публичные эндпоинты — `Depends(get_session)` из `async_session_factory()`
- `/me` эндпоинты — `Depends(get_current_user)` + `Depends(get_async_session)`
- `commit()` всегда в router
- `refresh()` после commit если нужен актуальный объект

---

## База данных — схемы PostgreSQL

| Схема | Назначение |
|---|---|
| `users` | User, Session, согласия |
| `scales` | ScaleResult, MeasurementPoint (KDQOL) |
| `vitals` | BP, Pulse, Weight, Water |
| `education` | Lesson, LessonCard, LessonTest, прогресс |
| `sleep` | SleepRecord |
| `medications` | MedicationPrescription, MedicationIntake |
| `kdqol` | KDQOL-SF точки измерения |
| `practices` | Practice, PracticeCompletion |
| `routine` | BaselineRoutine, DailyPlan, DailyVerification |
| `public` | alembic_version, Center, DialysisSchedule |

**Ключевые FK:** все таблицы с `patient_id` или `user_id` ссылаются на `users.users.id`

---

## Правила — что НЕ делать

1. **Alembic миграции** — не генерировать и не применять без явной команды. Только `alembic revision --autogenerate` и `alembic upgrade head` по запросу.
2. **Схемы БД** — не менять `__table_args__` schema без уточнения.
3. **Бизнес-логика в router** — не писать валидацию или обработку данных прямо в эндпоинтах.
4. **commit() в crud/service** — коммит только в router.
5. **gpt_support/** — модуль-заглушка, не трогать без явной задачи.
6. **Не удалять расписания диализа** — soft-close паттерн (закрытие, не удаление).

---

## Статус модулей

### Готово (production-ready)
- `auth/` — авторизация, сессии, PIN
- `users/` — пользователи, онбординг
- `vitals/` — АД, пульс, вес, вода
- `scales/` — HADS, KOP-25A, PSQI, PSS-10, WCQ, KDQOL-SF
- `education/` — уроки, карточки, тесты
- `practices/` — самостоятельные практики
- `medications/` — назначения и приёмы
- `routine/` — распорядок дня (МКФ d230)
- `sleep_tracker/` — рутинная оценка сна
- `dialysis/` — центры, расписания, CSV-импорт
- `researchers/` — панель исследователя
- `consent/` — согласия ПДн

### В разработке / заглушки
- `gpt_support/` — GPT-интеграция (RAG, агенты)
- `notifications/` — уведомления
- `doctor/` frontend — панель врача

### Roadmap (не начато)
- RAG-система с персонализацией
- Агенты: Coordinator, RAG, Motivator, Education
- Rehab Metrics (МКФ домены b130, b152, b164, d230, d570)

---

## Запуск

```bash
uvicorn app.main:app --reload          # API
python -m app.bots.tg_bot.main         # Telegram-бот
pytest                                  # Тесты
alembic upgrade head                    # Миграции (только по запросу)
```

---

## Контекст для новых задач

Когда получаешь задачу — уточни:
1. В каком модуле работаем?
2. Нужна ли Alembic миграция?
3. Это новый модуль или расширение существующего?

Придерживайся паттернов из `app/vitals/` как эталона.
