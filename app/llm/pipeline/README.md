# LLM Pipeline - Модульная архитектура

## Обзор

Модульный pipeline для обработки LLM запросов, заменяющий монолитную функцию `generate_response()`.

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                        LLMPipeline                          │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 1: Classification                                    │
│  - Классификация типа запроса (SAFETY, CLINICAL, EMOTIONAL)│
│  - Выбор модели (Lite, Pro, Max)                           │
│  - Определение домена (sleep, emotion, routine)            │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 2: Context                                           │
│  - Сбор витальных показателей, лекарств, сна               │
│  - RAG поиск релевантных материалов                        │
│  - Чтение ST/LT памяти                                     │
│  - Построение patient summary                              │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 3: Intake                                            │
│  - Парсинг сообщения (настроение, витальные)               │
│  - Анализ проблемы и намерения                             │
│  - Определение необходимости кларификации                  │
│  - Применение ST-memory для follow-up                      │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 4: Orchestration                                     │
│  - Router: выбор specialist-агентов                        │
│  - Specialists: psych_support, education, routine          │
│  - Composer: сборка финального ответа                      │
│  - Critic: проверка на нарушения                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 5: Validation                                        │
│  - Проверка на нежелательные паттерны                      │
│  - Rewrite при необходимости                               │
│  - Проверка prompt leakage                                 │
│  - Добавление crisis postfix для SAFETY                    │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│  Stage 6: Memory Write                                      │
│  - Создание memory candidates                              │
│  - Фильтрация через memory writer policy                   │
│  - Запись в ST/LT память                                   │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
                        LLMResponse
```

## Использование

### Базовое использование

```python
from app.llm.pipeline import LLMPipeline, LLMRequest

pipeline = LLMPipeline()

request = LLMRequest(
    patient_id=1,
    user_input="не могу уснуть",
    source="text",
    db=db_session,
)

response = await pipeline.process(request)
print(response.response)
```

### С дополнительным контекстом

```python
request = LLMRequest(
    patient_id=1,
    user_input="не могу уснуть",
    source="text",
    session_id="session_123",
    thread_id="thread_456",
    daily_context="Сегодня диализ",
    history=[
        {"role": "user", "content": "как дела?"},
        {"role": "assistant", "content": "Привет! Как ты?"},
    ],
    orchestration_mode="llm_full",
    db=db_session,
)

response = await pipeline.process(request)
```

### Обратная совместимость

```python
from app.llm.agent_v2 import generate_response_v2

# Старый API
result = await generate_response_v2(
    patient_id=patient_id,
    user_input=user_input,
    router_result=router_result,
    context=context,
    db=db,
)
```

## Типы данных

### LLMRequest

```python
@dataclass
class LLMRequest:
    patient_id: int
    user_input: str
    source: str = "text"  # "text" | "button" | "system"
    session_id: str | None = None
    thread_id: str | None = None
    daily_context: str = ""
    history: list[dict] = field(default_factory=list)
    orchestration_mode: str = "llm_full"
    db: AsyncSession | None = None
```

### LLMResponse

```python
@dataclass
class LLMResponse:
    response: str
    tokens_input: int
    tokens_output: int
    model: str
    domain: str | None
    response_time_ms: int
    account_id: str | None
    requested_model_tier: str
    actual_model_tier: str | None
    pending_vitals: list[dict] | None = None
    pending_st_memory: list[dict] = field(default_factory=list)
    pending_lt_memory: list[dict] = field(default_factory=list)
    diagnostics: dict[str, Any] = field(default_factory=dict)
```

### PipelineContext

```python
@dataclass
class PipelineContext:
    request: LLMRequest
    classification: RouterResult | None = None
    patient_context: dict[str, Any] = field(default_factory=dict)
    memory_reads: dict[str, Any] = field(default_factory=dict)
    parser_result: dict[str, Any] = field(default_factory=dict)
    intake_result: Any = None
    orchestration_result: Any = None
    validation_result: Any = None
    diagnostics: dict[str, Any] = field(default_factory=dict)
    should_skip_orchestration: bool = False
    early_response: str | None = None
    early_response_source: str | None = None
```

## Расширение

### Создание custom stage

```python
from app.llm.pipeline.types import PipelineStage, PipelineContext

class MyStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "my_stage"