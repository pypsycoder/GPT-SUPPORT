# Актуальная схема `generate_response_v2`

Документ описывает фактический runtime-flow для [`app/llm/agent_v2.py`](app/llm/agent_v2.py) и [`app/llm/pipeline/pipeline.py`](app/llm/pipeline/pipeline.py).

Главное изменение по сравнению со старой схемой: в `generate_response_v2` supervisor больше не является только ранним ambiguity-check. Для обычных текстовых сообщений он стал основным путём генерации ответа, а legacy orchestration остаётся в основном для `SAFETY` и `QUICK_ACTION`.

---

## Короткий итог

- `generate_response_v2()` создаёт `LLMRequest` и передаёт его в `LLMPipeline.process()`.
- `BoundaryGuardStage` по-прежнему стоит самым первым и может завершить pipeline через `early_response`.
- `ClassificationStage` использует `request.router_result`, если он уже передан в `generate_response_v2`; иначе вызывает `classify_request()` сам.
- `SupervisorStage` активен для всех запросов, кроме `SAFETY` и `QUICK_ACTION`.
- Для обычного текста supervisor сам строит `reply`, обновляет `supervisor_state` и выключает legacy orchestration.
- При supervisor-turn stages `context`, `intake` и `orchestration` не работают по своей основной логике, а только пишут `skipped` в diagnostics.
- `ValidationStage` всё равно выполняется и проверяет supervisor draft, но LLM-rewrite для supervisor-ответа сейчас не делает: при trigger такой draft сохраняется как есть.
- `MemoryWriteStage` выполняется и для supervisor path, и для legacy path.
- Финальный ответ в `generate_response_v2` собирается по приоритету: `early_response` -> `response_draft` -> `orchestration_result` -> fallback error.

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
   |                        source=boundary_guard_direct
   |                        or boundary_guard_combined
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
|   -> handle_message() |
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
   |                        source=clarifier
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
| rewrite policy        |
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

## Реально активные ветки

### 1. Normal text -> supervisor path

Это теперь основной путь для обычных текстовых сообщений.

```text
User input
  -> boundary_guard
  -> classification
  -> supervisor.handle_message()
  -> context: skipped(reason=supervisor_turn)
  -> intake: skipped(reason=supervisor_turn)
  -> orchestration: skipped(reason=supervisor_turn)
  -> validation on supervisor draft
  -> memory_write
  -> final response from response_draft
```

Что важно:

- `SupervisorStage` выставляет `context.supervisor_turn`.
- `context.response_draft = turn.reply`.
- `context.supervisor_state = turn.updated_state.to_dict()`.
- `context.should_skip_orchestration = True`.
- `account_id` в финальном ответе будет `SUPERVISOR`.
- `tokens_input` и `tokens_output` для такого ответа будут `0`, потому что ответ берётся не из legacy orchestration result.

### 2. Safety / quick action -> legacy path

Для `RequestType.SAFETY` и `RequestType.QUICK_ACTION` supervisor сейчас отключён.

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

- `SAFETY` не short-circuit после classification.
- `ValidationStage` дописывает crisis postfix к safety-ответу.
- Для `SAFETY` rewrite не запускается: статус в diagnostics будет `skipped_safety`.
- Для `QUICK_ACTION` context builder получает пустой `rag_query`.

### 3. Early exit path

Есть только два реальных ранних выхода:

- `boundary_guard` -> `early_response`
- `intake` -> `early_response` с `source=clarifier`

Supervisor в текущем `v2` не использует `early_response`. Он пишет ответ в `response_draft`, после чего pipeline формально продолжает выполнение до `validation` и `memory_write`.

---

## Что делает каждый stage в `v2`

| Stage | Статус | Что делает | Может завершить ответ |
|---|---|---|---|
| `boundary_guard` | Активен | Ищет prompt injection и запросы на раскрытие инструкций | Да, через `early_response` |
| `classification` | Активен | Берёт `router_result` из запроса или сам вызывает `classify_request()`; инициализирует `supervisor_state` | Нет |
| `supervisor` | Активен | Для normal text запускает `SupervisorOrchestrator.handle_message()` и формирует основной draft ответа | Нет, но переводит pipeline в supervisor path |
| `context` | Активен | На legacy path собирает patient context, RAG и memory reads; на supervisor path ставит `skipped` | Нет |
| `intake` | Активен | На legacy path запускает parser и `analyze_help_intake()`; на supervisor path ставит `skipped` | Да, через `early_response` |
| `orchestration` | Активен | На legacy path вызывает `run_full_llm_orchestration()` или `run_specialist_grounding_probe()` | Нет |
| `validation` | Активен | Валидирует draft/response, добавляет safety postfix, при необходимости пытается rewrite | Нет |
| `memory_write` | Активен | Строит memory candidates и решения по ST/LT записи | Нет |

---

## Как именно работает supervisor в `generate_response_v2`

`SupervisorStage` вызывает `SupervisorOrchestrator.handle_message()` и получает `SupervisorTurnResult`.

Внутри этого turn-а есть три ключевых сценария:

1. Есть `pending_question`, и текущий ответ можно распарсить как short answer.
2. Нужна кларификация, тогда supervisor возвращает новый вопрос и сохраняет `pending_question` в state.
3. Кларификация не нужна, тогда supervisor выбирает expert-агентов, синтезирует итоговый reply и обновляет state.

То есть supervisor в `v2` отвечает не только за "уточнить или не уточнить", а за весь stateful turn:

- определяет `message_type`
- обновляет `domain`, `intent`, `goal`
- копит `risk_flags`, `signals`, `facts`
- управляет `pending_question`
- выбирает `selected_agents`
- возвращает `state_delta`
- формирует финальный `reply`

---

## Как строится финальный ответ

`LLMPipeline._build_response()` собирает ответ в таком порядке:

1. Если есть `early_response`, возвращается он.
2. Иначе если есть `response_draft`, возвращается он.
3. Иначе если есть `orchestration_result`, берётся `final_response`.
4. Иначе возвращается fallback `"Извините, произошла ошибка при обработке запроса."`

Следствие:

- На supervisor path приоритет всегда у `response_draft`.
- На legacy path после orchestration и validation финальный текст тоже обычно лежит в `response_draft`, потому что `ValidationStage` сохраняет туда результат.
- `supervisor_state` и `supervisor_state_delta` пробрасываются наружу в старый API contract.

---

## Что возвращает `generate_response_v2`

Снаружи `generate_response_v2()` всё ещё отдаёт dict старого формата, но теперь внутри него есть supervisor-specific поля:

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

Это значит, что диаграмму и отладку нужно читать уже не как "legacy LLM + optional supervisor gate", а как "stateful supervisor-first pipeline с fallback на legacy orchestration".

---

## Что в старой схеме было неактуально

- Supervisor больше не стоит описывать как "ранняя кларификация до context".
- Неверно говорить, что normal text после supervisor идёт в обычный `context -> intake -> orchestration`.
- Неверно считать, что supervisor завершает pipeline через `early_response`.
- Неверно считать, что legacy orchestration остаётся основным генератором ответа для всех типов запросов.

Актуальная формулировка такая:

> В `generate_response_v2` supervisor является основным runtime-путём для обычных текстовых запросов, а legacy orchestration используется как отдельная совместимая ветка для `SAFETY` и `QUICK_ACTION`.

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
