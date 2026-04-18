# Актуальная схема `generate_response_v2`

Документ описывает фактический runtime-flow для [`app/llm/agent_v2.py`](app/llm/agent_v2.py), [`app/llm/pipeline/pipeline.py`](app/llm/pipeline/pipeline.py) и нового stateful supervisor-path.

Главное изменение по сравнению со старой схемой:

- `SupervisorStage` больше не является только ранним ambiguity-check.
- Для обычных текстовых сообщений именно supervisor стал основным путем генерации ответа.
- Перед самим orchestration-turn supervisor теперь делает обязательный LLM analysis.
- Analysis больше не требует JSON. Вместо этого используется line-based field protocol с локальной валидацией и retry до 3 попыток.
- Legacy orchestration остается отдельной совместимой веткой в основном для `SAFETY` и `QUICK_ACTION`.

---

## Короткий итог

- `generate_response_v2()` создает `LLMRequest` и передает его в `LLMPipeline.process()`.
- `BoundaryGuardStage` по-прежнему стоит первым и может завершить pipeline через `early_response`.
- `ClassificationStage` использует `request.router_result`, если он уже передан в `generate_response_v2`; иначе вызывает `classify_request()` сам.
- `ClassificationStage` также seed'ит `supervisor_state`.
- `SupervisorStage` активен для всех запросов, кроме `SAFETY` и `QUICK_ACTION`.
- На supervisor-path stage делает 2 LLM-вызова:
  - `goal_analysis` по field protocol
  - финальный `supervisor_draft rewrite`
- Оба вызова обязательны. Runtime fallback сейчас нет.
- Если `goal_analysis` возвращает невалидный payload, stage делает retry до 3 раз.
- Diagnostics сохраняют:
  - `attempts_total`
  - `succeeded_on_attempt`
  - `failures[]`
  - `final_status`
- После supervisor-turn stages `context`, `intake` и `orchestration` не выполняют свою основную legacy-логику, а пишут `skipped`.
- `ValidationStage` все равно выполняется и валидирует уже `response_draft`.
- `MemoryWriteStage` выполняется и для supervisor-path, и для legacy-path.

---

## Полный flow

```text
generate_response_v2(...)
  |
  v
build LLMRequest
  - patient_id
  - user_input
  - source / session_id / thread_id
  - daily_context / history
  - orchestration_mode
  - supervisor_state
  - router_result
  - db
  |
  v
LLMPipeline.process(request)
  |
  v
+-----------------------+
| Stage 0: BOUNDARY     |
| GUARD                 |
|-----------------------|
| prompt injection      |
| direct / combined     |
| pattern checks        |
+-----------------------+
   | hit
   +----------------------> EARLY RESPONSE
   |
   v pass
+-----------------------+
| Stage 1:              |
| CLASSIFICATION        |
|-----------------------|
| router_result or      |
| classify_request()    |
| seed supervisor_state |
+-----------------------+
   |
   v
+-----------------------+
| Stage 1.5:            |
| SUPERVISOR            |
|-----------------------|
| if SAFETY/QUICK_ACTION|
|   -> disabled         |
| else                  |
|   -> LLM goal analysis|
|   -> retries x3       |
|   -> orchestrator     |
|   -> optional prefetch|
|   -> LLM rewrite      |
|   -> response_draft   |
|   -> state_delta      |
|   -> skip legacy path |
+-----------------------+
   | legacy_path
   | for SAFETY / QUICK_ACTION
   v
+-----------------------+
| Stage 2: CONTEXT      |
|-----------------------|
| build_context_bundle  |
| optimized by default  |
| RAG + ST/LT reads     |
+-----------------------+
   |
   v
+-----------------------+
| Stage 3: INTAKE       |
|-----------------------|
| optional parser       |
| analyze_help_intake() |
| may return clarifier  |
+-----------------------+
   | clarification
   +----------------------> EARLY RESPONSE
   |
   v
+-----------------------+
| Stage 4:              |
| ORCHESTRATION         |
|-----------------------|
| legacy LLM path       |
| llm_full /            |
| specialist_rag / else |
+-----------------------+
   |
   v
+-----------------------+
| Stage 5: VALIDATION   |
|-----------------------|
| safety postfix        |
| validate draft/result |
+-----------------------+
   |
   v
+-----------------------+
| Stage 6: MEMORY WRITE |
|-----------------------|
| ST/LT candidates      |
| decisions + proposals |
+-----------------------+
   |
   v
_build_response()
  |
  v
old API dict from generate_response_v2
```

---

## Новый supervisor flow

### 1. LLM goal analysis

Перед тем как supervisor решает, нужен clarify или можно сразу помогать, stage делает отдельный analysis-вызов к LLM.

Этот вызов больше не возвращает JSON.

Вместо этого модель обязана вернуть field block:

```text
goal: ...
goal_status: ...
needs_clarification: true|false
clarification_question: ...
clarification_reason: ...
enough_context_for_support: true|false
enough_context_for_plan: true|false
state_hints.signals: ...
state_hints.risk_flags: ...
state_hints.facts: ...
state_hints.domain: ...
state_hints.intent: ...
```

После этого local validator:

- парсит field block
- проверяет обязательные поля
- проверяет enum / boolean значения
- собирает normalized analysis dict

Если payload невалиден:

- retry до 3 попыток
- ошибка каждой попытки пишется в `goal_analysis.failures[]`
- после 3 неудач чат-ход падает с `supervisor goal analysis failed after 3 attempts`

### 2. Clarification ownership

Supervisor по-прежнему принимает LLM как источник истины для:

- `goal`
- `goal_status`
- `needs_clarification`
- `clarification_question`
- `clarification_reason`
- `enough_context_for_support`
- `enough_context_for_plan`

Но сам `SupervisorOrchestrator` остается детерминированным исполнителем решения:

- merge state
- slot fill
- enforce hard cap
- route experts
- synthesize deterministic draft

### 3. Response modes

Из LLM analysis и текущего state supervisor выбирает один из runtime-режимов:

- `clarify_only`
- `hybrid_clarify`
- `direct_support`
- `direct_plan`

Правила:

- `generic_distress` обычно ведет в `hybrid_clarify`
- если контекст уже anchored и достаточен, идет `direct_support` или `direct_plan`
- после cap `5` clarify-ходов подряд supervisor принудительно прекращает clarify и дает best-effort help

### 4. Final reply

После deterministic supervisor draft stage делает обязательный LLM rewrite.

То есть реальный happy-path теперь такой:

```text
classification seed
  -> LLM goal analysis
  -> SupervisorOrchestrator.handle_message()
  -> optional support-context prefetch
  -> LLM rewrite of supervisor draft
  -> validation
  -> memory_write
```

---

## Реально активные ветки

### 1. Normal text -> supervisor path

Это основной путь для обычных текстовых сообщений.

```text
User input
  -> boundary_guard
  -> classification
  -> supervisor goal analysis
  -> supervisor.handle_message()
  -> optional context prefetch for support grounding
  -> supervisor rewrite
  -> context: skipped(reason=supervisor_turn)
  -> intake: skipped(reason=supervisor_turn)
  -> orchestration: skipped(reason=supervisor_turn)
  -> validation on response_draft
  -> memory_write
  -> final response from response_draft
```

Что важно:

- `SupervisorStage` выставляет `context.supervisor_turn`.
- `context.response_draft` заполняется уже после LLM rewrite.
- `context.supervisor_state = turn.updated_state.to_dict()`.
- `context.should_skip_orchestration = True`.
- `account_id` в финальном ответе будет `SUPERVISOR`.

### 2. Safety / quick action -> legacy path

Для `RequestType.SAFETY` и `RequestType.QUICK_ACTION` supervisor сейчас отключен.

```text
User input
  -> boundary_guard
  -> classification
  -> supervisor skipped(reason=legacy_path)
  -> context
  -> intake
  -> orchestration
  -> validation
  -> memory_write
```

Особенности:

- `ValidationStage` дописывает safety postfix к safety-ответу.
- Для `SAFETY` rewrite не запускается: статус в diagnostics будет `skipped_safety`.
- Для `QUICK_ACTION` context builder получает пустой `rag_query`.

### 3. Early exit path

Реальные ранние выходы сейчас такие:

- `boundary_guard` -> `early_response`
- `intake` -> `early_response` с `source=clarifier`

Supervisor сам не использует `early_response`.
Он пишет результат в `response_draft`, после чего pipeline формально продолжает выполнение до `validation` и `memory_write`.

---

## Что именно делает supervisor в текущей версии

`SupervisorStage` состоит из 4 крупных шагов.

### A. Goal analysis

Stage вызывает `_extract_goal_analysis(...)`.

Внутри:

- LLM получает `user_message`
- текущий `CurrentState`
- `pending_question`
- `clarification_streak`
- signals / risk_flags / facts

И возвращает analysis по field protocol.

### B. Analysis validation

Local validator проверяет не только формат, но и quality guards:

- anchored follow-up не может быть помечен как `generic_distress`
- anchored clarification question не должен уходить в side detail
- clarify-question при anchor должен оставаться внутри уже известного контекста

Примеры guard'ов:

- `жду диализ` + `goal_status=generic_distress` -> invalid analysis -> retry
- `жду диализ` + вопрос `как часто у тебя диализ?` -> invalid analysis -> retry

### C. Deterministic orchestration

Потом `SupervisorOrchestrator.handle_message()`:

- различает `short_answer`, `full_message`, `meta_message`, `correction`
- умеет slot-fill по `pending_question`
- merge'ит state delta
- при необходимости создает новый `pending_question`
- выбирает `response_mode`
- под hard cap `5` прекращает endless clarify-loop
- вызывает максимум нужных expert-agents

### D. Final rewrite

После этого stage:

- может подтянуть support-grounding через optimized context builder
- передает supervisor draft и normalized analysis в final LLM rewrite
- сохраняет уже rewritten text в `response_draft`

---

## Clarification policy v4

### Generic distress

Если пользователь пишет что-то вроде:

- `мне тревожно`
- `страшно`
- `мне плохо`

без причины и без контекста, ожидается:

- `goal_status = generic_distress`
- `needs_clarification = true`
- обычно `response_mode = hybrid_clarify`

То есть ответ должен быть:

- короткая валидирующая фраза
- один безопасный micro-step
- один открытый вопрос

### Anchored context

Если пользователь дает anchor:

- `жду диализ`
- `перед диализом`
- `не выпил таблетки`
- `боюсь, что подскочит давление`

это уже не должно считаться `generic_distress`.

Допустимы варианты:

- `resolved`
- `context_missing`

Но не `generic_distress`.

### Clarification question quality

Если контекст уже anchored, но clarify все еще нужен:

- вопрос должен оставаться внутри anchor
- вопрос должен быть открытым
- вопрос не должен уходить в side detail

Хорошо:

- `Что в предстоящем диализе тревожит тебя сильнее всего?`

Плохо:

- `Как часто у тебя диализ?`
- `Сколько раз в неделю процедура?`

### Clarification cap

Если подряд накопилось `5` clarify-ходов:

- supervisor перестает задавать новые clarify-вопросы
- переключается в forced best-effort help
- пишет это в diagnostics как `forced_by_cap`

---

## Что делает каждый stage в `v2`

| Stage | Статус | Что делает | Может завершить ответ |
|---|---|---|---|
| `boundary_guard` | Активен | Ищет prompt injection и запросы на раскрытие инструкций | Да, через `early_response` |
| `classification` | Активен | Берет `router_result` из запроса или сам вызывает `classify_request()`; seed'ит `supervisor_state` | Нет |
| `supervisor` | Активен | Делает LLM goal analysis, retries/validation, deterministic orchestrator, final rewrite | Нет, но переводит pipeline в supervisor path |
| `context` | Активен | На legacy path собирает patient context, RAG и memory reads; на supervisor path ставит `skipped` | Нет |
| `intake` | Активен | На legacy path запускает parser и `analyze_help_intake()`; на supervisor path ставит `skipped` | Да, через `early_response` |
| `orchestration` | Активен | На legacy path вызывает `run_full_llm_orchestration()` или `run_specialist_grounding_probe()` | Нет |
| `validation` | Активен | Валидирует `response_draft` или orchestration-result, добавляет safety postfix | Нет |
| `memory_write` | Активен | Строит memory candidates и решения по ST/LT записи | Нет |

---

## Как строится финальный ответ

`LLMPipeline._build_response()` собирает ответ в таком порядке:

1. Если есть `early_response`, возвращается он.
2. Иначе если есть `response_draft`, возвращается он.
3. Иначе если есть `orchestration_result`, берется `final_response`.
4. Иначе возвращается fallback error.

Следствие:

- На supervisor path приоритет всегда у `response_draft`.
- На legacy path после orchestration и validation финальный текст тоже обычно лежит в `response_draft`.
- `supervisor_state` и `supervisor_state_delta` пробрасываются наружу в старый API contract.

---

## Что возвращает `generate_response_v2`

Снаружи `generate_response_v2()` все еще отдает dict старого формата, но теперь внутри него есть supervisor-specific поля:

- `response`
- `tokens_input`
- `tokens_output`
- `model`
- `domain`
- `response_time_ms`
- `account_id`
- `requested_model_tier`
- `actual_model_tier`
- `pending_vitals`
- `pending_st_memory`
- `pending_lt_memory`
- `supervisor_state`
- `supervisor_state_delta`
- `diagnostics`

---

## Что стало неактуально в старой схеме

- Supervisor больше нельзя описывать как "ранняя кларификация до context".
- Неверно говорить, что normal text после supervisor идет в обычный `context -> intake -> orchestration`.
- Неверно считать, что supervisor завершает pipeline через `early_response`.
- Неверно считать, что JSON является wire-format'ом для goal analysis.
- Неверно считать, что supervisor не валидирует semantic consistency anchored follow-up.

Актуальная формулировка:

> В `generate_response_v2` supervisor является основным runtime-путем для обычных текстовых запросов. Перед самим turn orchestration он делает обязательный LLM analysis по field protocol, локально валидирует результат, при необходимости делает retry, затем исполняет stateful turn и пишет финальный ответ через LLM rewrite. Legacy orchestration остается отдельной совместимой веткой для `SAFETY` и `QUICK_ACTION`.

---

## Ссылки на код

- [`app/llm/agent_v2.py`](app/llm/agent_v2.py)
- [`app/llm/pipeline/pipeline.py`](app/llm/pipeline/pipeline.py)
- [`app/llm/pipeline/types.py`](app/llm/pipeline/types.py)
- [`app/llm/pipeline/stages/boundary_guard.py`](app/llm/pipeline/stages/boundary_guard.py)
- [`app/llm/pipeline/stages/classification.py`](app/llm/pipeline/stages/classification.py)
- [`app/llm/pipeline/stages/supervisor.py`](app/llm/pipeline/stages/supervisor.py)
- [`app/llm/pipeline/stages/context.py`](app/llm/pipeline/stages/context.py)
- [`app/llm/pipeline/stages/intake.py`](app/llm/pipeline/stages/intake.py)
- [`app/llm/pipeline/stages/orchestration.py`](app/llm/pipeline/stages/orchestration.py)
- [`app/llm/pipeline/stages/validation.py`](app/llm/pipeline/stages/validation.py)
- [`app/llm/pipeline/stages/memory_write.py`](app/llm/pipeline/stages/memory_write.py)
- [`app/llm/supervisor/orchestrator.py`](app/llm/supervisor/orchestrator.py)
- [`tests_py/llm/test_pipeline.py`](tests_py/llm/test_pipeline.py)
- [`tests_py/llm/test_trace_humanizer.py`](tests_py/llm/test_trace_humanizer.py)
