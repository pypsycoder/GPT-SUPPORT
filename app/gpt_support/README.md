# `gpt_support`

Эта директория больше не является боевым LLM-runtime.

Актуальная архитектура LLM-слоя живет в `app/llm/` и использует один текущий pipeline без legacy-веток и adapter-слоя.

## Где теперь runtime

Основные точки входа:

- `app/routers/chat.py`
- `app/researchers/router.py`
- `app/llm/proactive.py`

Во всех трех местах создается `LLMRequest`, после чего запрос уходит напрямую в `LLMPipeline.process(...)`.

## Текущий pipeline

Актуальная последовательность стадий:

1. `boundary_guard`
2. `classification`
3. `supervisor`
4. `memory_write`

Коротко по ответственности:

- `boundary_guard`
  режет prompt-injection и может завершить ход через `early_response`
- `classification`
  определяет `request_type`, `model_tier`, `domain_hint`
- `supervisor`
  запускает Graph v2 и формирует финальный `response_draft`
- `memory_write`
  нормализует memory-диагностику и pending memory writes

## Что внутри supervisor

Внутри `SupervisorStage` работает Graph v2:

1. `intake_analyze`
2. `intake_validate`
3. `intake_execute`
4. `delegation_analyze`
5. `delegation_validate`
6. `invoke_emotional_expert`
7. `finalize_reply`

Если пациент делегирован на эксперта, это все равно остается частью того же текущего pipeline. Отдельного legacy-orchestration пути больше нет.

## Какие модули сейчас важны

| Путь | Назначение |
|---|---|
| `app/llm/pipeline/` | `LLMPipeline`, стадии, типы запросов/ответов, актуальная структура runtime |
| `app/llm/langgraph_supervisor/` | Graph v2: intake, delegation, expert-flow |
| `app/llm/pool.py` | Пул аккаунтов и клиент провайдера |
| `app/llm/router.py` | Классификация запросов (`RequestType`, `RouterResult`) |
| `app/llm/proactive.py` | Проактивные сообщения, тоже через текущий pipeline |
| `app/llm/trace_humanizer.py` | Человекочитаемая трассировка diagnostics |

## Что удалено из runtime

Из актуального пути больше не используются:

- `app/llm/agent.py`
- `app/llm/agent_v2.py`
- legacy stages `context`, `intake`, `orchestration`, `validation`
- dict-adapter над `LLMPipeline`

## Где смотреть детали

- Подробная структура: `app/llm/pipeline/STRUCTURE.md`
- Краткая схема потока: `SUPERVISOR_FLOW_DIAGRAM.md`

Итог: `gpt_support/` теперь только вспомогательная директория, а не место, где живет актуальная LLM-архитектура.
