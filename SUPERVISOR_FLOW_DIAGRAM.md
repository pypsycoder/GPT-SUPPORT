# Актуальная схема LLM pipeline после включения Supervisor

Документ отражает текущее поведение кода после:

- включения `SupervisorStage` в активный `LLMPipeline`
- добавления `BoundaryGuardStage`
- перехода `ContextStage` на `build_context_bundle_optimized()` по умолчанию

## Короткий итог

- `BoundaryGuardStage` стоит самым первым stage и режет prompt injection до классификации.
- `SupervisorStage` теперь реально включен и выполняется между `classification` и `context`.
- `ContextStage` по умолчанию использует optimized context builder.
- Safety-запросы по-прежнему не short-circuit после классификации и проходят дальше по pipeline.
- Отдельный post-generation guard на prompt leakage все еще есть только в legacy `app/llm/agent.py`, а не в modular `ValidationStage`.

---

## Реально активный pipeline

```text
USER INPUT
   |
   v
+-----------------------+
| Stage 0: BOUNDARY     |
| GUARD                 |
|-----------------------|
| direct patterns       |
| action + target       |
| prompt requests       |
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
| classify_request()    |
| request_type          |
| model_tier            |
| domain_hint           |
| priority              |
+-----------------------+
   |
   v
+-----------------------+
| Stage 1.5:            |
| SUPERVISOR            |
|-----------------------|
| short/vague checks    |
| domain ambiguity      |
| intent ambiguity      |
| early clarification   |
+-----------------------+
   | clarify
   +----------------------> EARLY RESPONSE
   |                        source=supervisor
   |                        skip remaining stages
   |
   v pass
+-----------------------+
| Stage 2: CONTEXT      |
|-----------------------|
| optimized builder     |
| vitals / meds / sleep |
| RAG                   |
| ST/LT memory read     |
+-----------------------+
   |
   v
+-----------------------+
| Stage 3: INTAKE       |
|-----------------------|
| optional parser       |
| analyze_help_intake() |
| clarification_needed? |
+-----------------------+
   | yes
   +----------------------> EARLY RESPONSE
   |                        source=clarifier
   |                        skip orchestration
   |
   v no
+-----------------------+
| Stage 4:              |
| ORCHESTRATION         |
|-----------------------|
| llm_full / probe      |
| fallback -> full LLM  |
| generates response    |
+-----------------------+
   |
   v
+-----------------------+
| Stage 5: VALIDATION   |
|-----------------------|
| rewrite policy        |
| crisis postfix        |
| no dedicated          |
| prompt leak guard     |
+-----------------------+
   |
   v
+-----------------------+
| Stage 6: MEMORY WRITE |
|-----------------------|
| ST/LT candidates      |
| memory policy         |
+-----------------------+
   |
   v
FINAL RESPONSE
```

---

## Что делает каждый stage

| Stage | Статус | Что происходит | Early exit |
|---|---|---|---|
| `boundary_guard` | Активен | Ищет prompt injection и запросы на раскрытие системного prompt | Да |
| `classification` | Активен | Вызывает `classify_request()` и пишет `classify` в diagnostics | Нет |
| `supervisor` | Активен | Ранний ambiguity-check и clarification до `context` | Да |
| `context` | Активен | Использует optimized context builder, читает RAG и memory | Нет |
| `intake` | Активен | При необходимости запускает parser и делает clarification | Да |
| `orchestration` | Активен | Запускает основную LLM-оркестрацию | Нет |
| `validation` | Активен | Проверяет ответ на rewrite-правила, для safety дописывает hotline postfix | Нет |
| `memory_write` | Активен | Формирует кандидатов и решения по записи в память | Нет |

---

## Где стоит защита от prompt injection

### 1. До классификации

`BoundaryGuardStage` выполняется раньше всех остальных шагов.

Он ловит:

- прямые паттерны вроде `ignore previous instructions`, `system prompt`, `покажи промпт`
- комбинированные запросы вида `show/give/write + prompt/instructions`

При срабатывании:

- ставится `context.should_skip_orchestration = True`
- формируется безопасный отказ
- pipeline обрывается через `early_response`

### 2. После генерации ответа

В legacy-монолите `app/llm/agent.py` есть `_detect_prompt_leakage()` и отдельный post-generation guard.

В модульном pipeline этого отдельного шага сейчас нет:

- `ValidationStage` заявляет prompt leakage в комментарии
- фактически использует только `validate_response_for_rewrite()`
- `validate_response_for_rewrite()` не ищет утечку prompt

Итог: защита от prompt injection на входе уже работает в modular pipeline, а защита от prompt leakage на выходе пока не доведена до паритета с legacy.

---

## Safety flow в текущей реализации

Сейчас фактический путь safety-запроса выглядит так:

```text
User input
  -> boundary_guard (если это не prompt injection)
  -> classification => request_type=SAFETY, model_tier=MAX
  -> supervisor (skip: not_needed)
  -> context
  -> intake
  -> orchestration
  -> validation adds crisis postfix
  -> memory_write
```

Что важно:

- `classification` только маркирует запрос как `SAFETY`
- `supervisor` для safety не используется
- `orchestration` отключает ветки `llm_full` и `specialist_rag` для safety, но попадает в `else`
- в `else` сейчас вызывается `run_full_llm_orchestration()`
- в `validation` safety-ответу дописывается crisis postfix

Итог: safety сейчас не short-circuit, а проходит почти весь pipeline.

---

## Статус Supervisor

### Что есть в коде

В репозитории активны:

- `app/llm/supervisor.py`
- `app/llm/pipeline/stages/supervisor.py`
- rule-based и LLM-based режимы
- `should_use_supervisor()`

### Что реально подключено

Supervisor уже включен в runtime-поток:

```text
boundary_guard -> classification -> supervisor -> context
```

### Что делает сейчас

Supervisor нужен для раннего отсечения неоднозначных запросов:

- коротких и расплывчатых
- mixed-domain запросов
- mixed-intent запросов
- контекстных коротких follow-up без достаточной ясности

Если нужна кларификация, pipeline завершается раньше `context`, `intake` и `orchestration`.

---

## Что было исправлено при включении Supervisor

### 1. Supervisor подключен в `LLMPipeline`

Теперь stage реально исполняется, а не остается закомментированной заготовкой.

### 2. Исправлен bug в diagnostics

Раньше stage писал `mode/tokens_used` в `context.diagnostics["supervisor"]` до инициализации словаря.

Теперь diagnostics инициализируются заранее, поэтому stage можно безопасно держать включенным.

### 3. Обновлена rule-based логика ambiguity

Кейс `не могу уснуть и очень тревожно` теперь корректно определяется как `domain_ambiguity`.

### 4. Обновлены pipeline-тесты под optimized context builder

Тесты больше не мокают несуществующий `build_context_bundle` в модуле stage и работают с `build_context_bundle_optimized()`.

---

## Тестовый статус

Команда:

```text
pytest tests_py/llm/test_pipeline.py tests_py/llm/test_supervisor.py -q
```

Результат:

```text
24 passed
```

---

## Оставшиеся риски и следующие шаги

1. Решить, нужен ли safety short-circuit как в старой схеме, или текущий проход через orchestration является осознанным новым поведением.
2. Перенести post-generation prompt leak guard из `agent.py` в modular `ValidationStage` или в отдельный stage.
3. При необходимости расширить `should_use_supervisor()` дополнительными эвристиками для follow-up и mixed-intent кейсов.
4. Держать диаграмму синхронной с runtime-flow при следующих изменениях stages.

---

## Ссылки на код

- [`app/llm/pipeline/pipeline.py`](app/llm/pipeline/pipeline.py)
- [`app/llm/pipeline/stages/boundary_guard.py`](app/llm/pipeline/stages/boundary_guard.py)
- [`app/llm/pipeline/stages/supervisor.py`](app/llm/pipeline/stages/supervisor.py)
- [`app/llm/pipeline/stages/context.py`](app/llm/pipeline/stages/context.py)
- [`app/llm/pipeline/stages/intake.py`](app/llm/pipeline/stages/intake.py)
- [`app/llm/pipeline/stages/orchestration.py`](app/llm/pipeline/stages/orchestration.py)
- [`app/llm/pipeline/stages/validation.py`](app/llm/pipeline/stages/validation.py)
- [`app/llm/supervisor.py`](app/llm/supervisor.py)
- [`app/llm/agent.py`](app/llm/agent.py)
- [`tests_py/llm/test_pipeline.py`](tests_py/llm/test_pipeline.py)
- [`tests_py/llm/test_supervisor.py`](tests_py/llm/test_supervisor.py)
