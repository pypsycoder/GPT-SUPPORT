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
- L0 (`app/llm/router_l0.py`) детерминированно ловит кризис/острое медицинское
  состояние и может завершить pipeline через `early_response`.

### 2. `classification`

- определяет `request_type`, `model_tier`, `domain_hint` (каскад L0→L1→L2,
  см. `app/llm/router_cascade.py`);
- инициализирует `supervisor_state`.

### 3. `supervisor`

- один структурный вызов агента (`app/llm/agent/loop.py`, `Agent.run()`)
  вместо цепочки intake → delegation → expert;
- модель возвращает плоскую карточку `AgentReply` (текст + intent, safety,
  technique_id, memory_candidates) одним вызовом;
- второй эшелон защиты (`_apply_agent_safety_net`) перекрывает ответ протоколом,
  если агент сам поднял `safety_level=urgent`;
- строит финальный `response_draft`, обновляет `supervisor_state`, пишет
  диагностику хода.

### 4. `memory_write`

- нормализует memory-диагностику;
- сохраняет кандидатов в устойчивую память из `AgentReply.memory_candidates`.

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
- `app/llm/langgraph_supervisor/` (Graph v2: intake → delegation → expert) —
  заменена одноагентной веткой выше, флаг `LLM_SINGLE_AGENT` убран за
  ненадобностью (единственная ветка теперь всегда активна)
