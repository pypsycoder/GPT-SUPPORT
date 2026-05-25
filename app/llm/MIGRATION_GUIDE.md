# Migration Guide: Переход на модульный LLM Pipeline

## Обзор изменений

Монолитная функция `generate_response()` (1627 строк) была разбита на модульный pipeline из 6 независимых stages:

1. **Classification** - классификация и safety
2. **Context** - сбор контекста и памяти
3. **Intake** - анализ и кларификация
4. **Orchestration** - генерация ответа
5. **Validation** - валидация и rewrite
6. **Memory Write** - запись в память

## Преимущества новой архитектуры

### ✅ Тестируемость
- Каждый stage тестируется отдельно
- Легко мокировать зависимости
- Изолированные unit-тесты

### ✅ Модульность
- Stages независимы друг от друга
- Легко добавлять новые stages
- Можно переключать реализации

### ✅ Читаемость
- Явные границы ответственности
- Понятный flow данных
- Меньше cognitive load

### ✅ Отладка
- Логи по каждому stage
- Диагностика на каждом этапе
- Легко найти проблему

## Как использовать новый pipeline

### Вариант 1: Через обертку (рекомендуется для начала)

```python
from app.llm.agent_v2 import generate_response_v2

# Полностью совместимо со старым API
result = await generate_response_v2(
    patient_id=patient_id,
    user_input=user_input,
    router_result=router_result,  # Не используется, но для совместимости
    context=context,
    db=db,
)
```

### Вариант 2: Напрямую через pipeline

```python
from app.llm.pipeline import LLMPipeline, LLMRequest

pipeline = LLMPipeline()

request = LLMRequest(
    patient_id=patient_id,
    user_input=user_input,
    source="text",
    session_id=session_id,
    thread_id=thread_id,
    db=db,
)

response = await pipeline.process(request)
```

## Миграция существующего кода

### Шаг 1: Добавить feature flag

```python
# config.py
USE_NEW_PIPELINE = os.getenv("LLM_USE_NEW_PIPELINE", "false").lower() == "true"
```

### Шаг 2: Обновить endpoint

```python
# app/llm/router.py или где вызывается generate_response

from config import USE_NEW_PIPELINE
from app.llm.agent import generate_response  # старая версия
from app.llm.agent_v2 import generate_response_v2  # новая версия

if USE_NEW_PIPELINE:
    result = await generate_response_v2(patient_id, user_input, router_result, context, db)
else:
    result = await generate_response(patient_id, user_input, router_result, context, db)
```

### Шаг 3: Тестирование

1. Запустить с `LLM_USE_NEW_PIPELINE=false` (старая версия)
2. Собрать baseline метрики
3. Запустить с `LLM_USE_NEW_PIPELINE=true` (новая версия)
4. Сравнить метрики:
   - Латентность
   - Качество ответов
   - Ошибки
   - Использование токенов

### Шаг 4: Постепенный rollout

```python
# Канареечный деплой: 10% трафика на новый pipeline
import random

use_new = USE_NEW_PIPELINE or (random.random() < 0.1)

if use_new:
    result = await generate_response_v2(...)
else:
    result = await generate_response(...)
```

### Шаг 5: Полная миграция

После успешного тестирования:

1. Установить `LLM_USE_NEW_PIPELINE=true` по умолчанию
2. Удалить старую `generate_response()` через несколько недель
3. Переименовать `generate_response_v2` → `generate_response`

## Расширение pipeline

### Добавление нового stage

```python
from app.llm.pipeline.types import PipelineStage, PipelineContext

class MyCustomStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "my_custom_stage"
    
    async def process(self, context: PipelineContext) -> PipelineContext:
        # Ваша логика
        context.diagnostics["my_custom_stage"] = {
            "status": "ok",
        }
        return context
```

### Регистрация stage в pipeline

```python
# app/llm/pipeline/pipeline.py

class LLMPipeline:
    def __init__(self):
        self.stages = [
            ClassificationStage(),
            ContextStage(),
            MyCustomStage(),  # Добавляем новый stage
            IntakeStage(),
            OrchestrationStage(),
            ValidationStage(),
            MemoryWriteStage(),
        ]
```

### Условное выполнение stage

```python
class ConditionalStage(PipelineStage):
    async def process(self, context: PipelineContext) -> PipelineContext:
        # Пропускаем stage при определенных условиях
        if context.classification.request_type == RequestType.SAFETY:
            logger.info("[conditional] skipping for safety request")
            return context
        
        # Обычная обработка
        # ...
        return context
```

## Отладка и мониторинг

### Логи по stages

```python
# Каждый stage логирует свою работу
[classification] patient=1 type=emotional tier=pro domain=sleep
[context] patient=1 sections_ok=8 rag_hits=3 latency_ms=250
[intake] patient=1 problem=sleep_problem intent=sleep_support
[orchestration] patient=1 mode=llm_full route=psych_support tokens_in=150 tokens_out=80
[validation] patient=1 rewrite_needed reasons=['template_reassurance']
[memory_write] patient=1 candidates=4 st_entries=3 lt_entries=1
[pipeline] completed patient=1 total_latency_ms=3500
```

### Диагностика в response

```python
response = await pipeline.process(request)

# Диагностика по каждому stage
for stage_diag in response.diagnostics["stages"]:
    print(f"{stage_diag['name']}: {stage_diag['status']} ({stage_diag['latency_ms']}ms)")

# Детальная диагностика
print(response.diagnostics["classify"])
print(response.diagnostics["patient_context"])
print(response.diagnostics["orchestration"])
```

### Метрики

```python
from prometheus_client import Histogram

pipeline_stage_latency = Histogram(
    'llm_pipeline_stage_latency_seconds',
    'Latency per pipeline stage',
    ['stage_name', 'status']
)

# В каждом stage
with pipeline_stage_latency.labels(stage_name=self.stage_name, status="ok").time():
    context = await self.process(context)
```

## Обратная совместимость

Новый pipeline полностью совместим со старым API:

- ✅ Тот же формат входных данных
- ✅ Тот же формат ответа
- ✅ Те же diagnostics (расширенные)
- ✅ Та же логика обработки
- ✅ Те же промпты

Различия:

- ⚠️ Порядок некоторых проверок может отличаться
- ⚠️ Диагностика более детальная
- ⚠️ Логи структурированы по stages

## Производительность

Ожидаемые изменения:

- **Латентность**: без изменений (±5%)
- **Память**: +10-15% (дополнительные объекты context)
- **CPU**: без изменений
- **Читаемость кода**: +500% 😊

## Troubleshooting

### Проблема: Stage падает с ошибкой

```python
# Проверьте логи
[pipeline] stage=orchestration failed patient=1: LLMTransportError

# Проверьте diagnostics
response.diagnostics["stages"][-1]["error"]
```

### Проблема: Разные ответы в старом и новом pipeline

Возможные причины:

1. Разный порядок проверок (boundary guards)
2. Разная логика ST-memory continuation
3. Разные промпты (если обновлялись)

Решение: Сравнить diagnostics обеих версий

### Проблема: Медленнее старой версии

Проверьте:

1. Не добавлены ли лишние stages
2. Нет ли дублирования запросов к БД
3. Правильно ли работает кэширование

## Дальнейшие улучшения

После миграции можно добавить:

1. **Circuit breaker** для LLM вызовов
2. **Rate limiting** для аккаунтов
3. **Параллелизацию** context building
4. **Кэширование** patient summary
5. **A/B тестирование** разных промптов
6. **Адаптивную orchestration** (simple vs full)

## Контакты

Вопросы по миграции: @llm-team
Баги: создать issue в репозитории
Документация: `/docs/llm/pipeline/`
