# Current LLM Pipeline

Этот файл описывает актуальный runtime после удаления legacy-веток и adapter-слоя.

## Точки входа

- `app/routers/chat.py`
- `app/researchers/router.py`
- `app/llm/proactive.py`

Во всех трёх местах запросы теперь идут напрямую в `LLMPipeline.process(LLMRequest)`.

## Входной контракт

`LLMRequest` содержит только текущие runtime-поля:

- `patient_id`
- `user_input`
- `source`
- `supervisor_state`
- `router_result`
- `strict_model_tier`
- `db`

## Основной pipeline

Порядок стадий фиксированный:

1. `boundary_guard`
2. `classification`
3. `supervisor`
4. `memory_write`

### 1. `boundary_guard`

- режет prompt-injection и служебные запросы;
- может завершить pipeline через `early_response`.

### 2. `classification`

- определяет `request_type`, `model_tier`, `domain_hint`;
- инициализирует `supervisor_state`.

### 3. `supervisor`

- запускает Graph v2 через `run_first_module()`;
- строит финальный `response_draft`;
- обновляет `supervisor_state`;
- пишет полную диагностику subgraph.

Внутренний порядок supervisor graph:

1. `intake_analyze`
2. `intake_validate`
3. `intake_execute`
4. `delegation_analyze` при `DELEGATE`
5. `delegation_validate` при `DELEGATE`
6. `invoke_emotional_expert` при `DELEGATE`
7. `finalize_reply`

### 4. `memory_write`

- нормализует memory-диагностику;
- возвращает `pending_st_memory` и `pending_lt_memory`, если они появятся.

## Выходной контракт

`LLMResponse` собирается напрямую из:

- `early_response` из `boundary_guard`, либо
- `response_draft` из `supervisor`.

В ответе сохраняются:

- текст ответа;
- токены и модель;
- `supervisor_state` и `supervisor_state_delta`;
- полная `diagnostics`.

## Что удалено

- `app/llm/agent.py`
- `app/llm/agent_v2.py`
- legacy stages: `context`, `intake`, `orchestration`, `validation`
- dict-adapter между runtime и API-слоем
