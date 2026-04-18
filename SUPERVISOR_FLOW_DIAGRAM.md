# Current Supervisor Flow

Документ обновлен после удаления legacy LLM-пайплайна и adapter-слоя.

Актуальный runtime:

1. `app/routers/chat.py`, `app/researchers/router.py` и `app/llm/proactive.py`
   создают `LLMRequest` и вызывают `LLMPipeline.process(...)` напрямую.
2. `BoundaryGuardStage`
   делает раннюю защиту от prompt-injection и при необходимости завершает ход `early_response`.
3. `ClassificationStage`
   определяет `request_type`, `model_tier`, `domain_hint` и инициализирует `supervisor_state`.
4. `SupervisorStage`
   запускает Graph v2 (`run_first_module`) и формирует финальный `response_draft`.
5. `MemoryWriteStage`
   нормализует memory-диагностику и pending memory writes.
6. `LLMPipeline._build_response()`
   собирает итоговый `LLMResponse` напрямую из `early_response` или `response_draft`.

## Graph v2 внутри `SupervisorStage`

1. `intake_analyze`
2. `intake_validate`
3. `intake_execute`
4. `delegation_analyze` при `DELEGATE`
5. `delegation_validate` при `DELEGATE`
6. `invoke_emotional_expert` при `DELEGATE`
7. `finalize_reply`

## Что больше не используется

- `app/llm/agent.py`
- `app/llm/agent_v2.py`
- legacy stages `context`, `intake`, `orchestration`, `validation`
- dict-adapter поверх `LLMPipeline`

Подробная актуальная структура лежит в [app/llm/pipeline/STRUCTURE.md](app/llm/pipeline/STRUCTURE.md).
