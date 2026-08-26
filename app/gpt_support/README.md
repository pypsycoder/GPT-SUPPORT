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
  L0 детерминированно ловит кризис/острое медицинское состояние, режет prompt-injection и может завершить ход через `early_response`
- `classification`
  определяет `request_type`, `model_tier`, `domain_hint` (каскад L0→L1→L2)
- `supervisor`
  один структурный вызов агента (`AgentReply`) и формирует финальный `response_draft`
- `memory_write`
  нормализует memory-диагностику и pending memory writes

## Что внутри supervisor

`SupervisorStage` делает один структурный LLM-вызов вместо цепочки узлов: агент
(`app/llm/agent/loop.py`) получает промпт, собранный слоями (`prompt_assembly.py`,
префиксное кэширование), и возвращает плоскую карточку `AgentReply` — текст
ответа вместе с intent, safety-вердиктом, id техники и кандидатами в память.
Второй эшелон (`_apply_agent_safety_net`) перекрывает ответ протоколом, если
агент сам поднял `safety_level=urgent`.

## Какие модули сейчас важны

| Путь | Назначение |
|---|---|
| `app/llm/pipeline/` | `LLMPipeline`, стадии, типы запросов/ответов, актуальная структура runtime |
| `app/llm/agent/` | Одноагентная ветка: `loop.py` (вызов + ретраи), `schemas.py` (`AgentReply`), `prompts.py`, `techniques.py`, `judge.py` |
| `app/llm/pool.py` | Пул аккаунтов и клиент провайдера |
| `app/llm/router_cascade.py`, `router_l0.py`, `router_l1.py`, `router_l2.py` | Каскадная классификация запросов |
| `app/llm/router.py` | Синхронный keyword-роутер — фолбэк каскада (`RequestType`, `RouterResult`) |
| `app/llm/proactive.py` | Проактивные сообщения, тоже через текущий pipeline |
| `app/llm/trace_humanizer.py` | Человекочитаемая трассировка diagnostics |

## Что удалено из runtime

Из актуального пути больше не используются:

- `app/llm/agent.py`
- `app/llm/agent_v2.py`
- legacy stages `context`, `intake`, `orchestration`, `validation`
- dict-adapter над `LLMPipeline`
- `app/llm/langgraph_supervisor/` (Graph v2: intake → delegation → expert) —
  жила параллельно одноагентной ветке под флагом `LLM_SINGLE_AGENT`, теперь
  удалена вместе с флагом

## Где смотреть детали

- Подробная структура: `app/llm/pipeline/STRUCTURE.md`

Итог: `gpt_support/` теперь только вспомогательная директория, а не место, где живет актуальная LLM-архитектура.
