# План: LLM-классификатор суицид-риска (2-й эшелон после L0)

**Дата:** 2026-08-31
**Основание:** `CRISIS_SEMANTIC_VALIDATION.md` — embedding-слой не прошёл валидацию,
удалён. `safety-bench` рекомендует LLM-классификатор (арм `lite`, recall 0.81 / FPR 0.06),
в приложение не заведён.

**СТАТУС: реализовано 2026-08-31** (решения Дмитрия по §3, §6 учтены; §6.1 = вариант B).
- `app/llm/safety_classifier.py` + `app/llm/prompts/safety_classifier.txt` (рубрика из
  `lite_prompt_v2.md`).
- Ветка в `boundary_guard.py` (§3), плашки в `safety_responses.py`, поле
  `PipelineContext.safety_footer`, дописывание в `pipeline._build_response`, подсказка
  агенту в `supervisor._l0_note`, флаг `LLM_SAFETY_LLM` (default ON) в `.env.example`.
- Тесты: `tests_py/llm/test_safety_classifier.py` (15) + e2e (плашка / обрыв).
  Autouse-стаб `tests_py/llm/conftest.py` (маркер `real_safety_classifier` его снимает).
- Eval-скрипт `scripts/eval_safety_classifier.py`.

**Прогон против golden set, dev split (120 строк, L0 + LLM):**

| метрика | L0+LLM | было (L0 alone) | safety-bench `lite` |
|---|---|---|---|
| recall {act,plan}/self (жёсткая реакция) | **86%** | 43–68% | 0.81 |
| FPR `none` (жёсткая реакция) | **3%** (и то — L0 на слове «суицид» в новости; своя FPR LLM ≈ 0) | 4% | 0.06 |
| FPR `distress` (жёсткая реакция) | **0%** | 0% | — |
| recall passive/self (мягкая плашка+) | 72% | ~8% | — |

**Test-сплит (holdout, 181 стр., прогнан 2026-08-31 ночью, рубрика после НЕ менялась):**

| метрика | test | dev | safety-bench `lite` |
|---|---|---|---|
| recall {act,plan}/self (жёсткая реакция) | **90.9%** (50/55) | 86% | 0.81 |
| FPR `none` (жёсткая) | 4.2% (обе — L0 на слове «самоубийство» в абстрактном вопросе) | 3% | 0.06 |
| FPR `distress` (жёсткая) | 3.1% | 0% | — |
| recall passive/self | 63% | 72% | — |
| FPR other/abstract (жёсткая) | 23.7% | 12% | — |

**Recall 91% на holdout — выше цели 0.81.** patient-sim (`2026-09-01_night_safety_llm.md`):
классификатор сработал 2×, оба на суицид-сценариях, оба PASS; ложных кризис-эскалаций 0.

Открыто: рубрику стоит допилить на «пора заканчивать/закончить это всё» → `ideation_active`
(сейчас классификатор зовёт их `distress`, 3 из 5 пропущенных high-risk на test). Тюнить
на dev. Слабое место — abstract-обсуждение суицида (FPR other/abstract 24%).

---

## 1. Что берём из safety-bench

`safety-bench/adapters/lite.py` + `config/lite_prompt_v2.md` (рубрика 5 уровней).
**Не импорт из репо safety-bench** — он не мержится в приложение. Переносим:
- текст рубрики → `app/llm/prompts/safety_classifier.txt` (снимок `lite_prompt_v2.md`);
- логику вызова + разбор JSON → новый `app/llm/safety_classifier.py`.

**Контракт классификатора:**
- вход: `text` (реплика пациента) + `context: list[str]` (предыдущие реплики бота, опц.);
- выход: `level ∈ {none, distress, ideation_passive, ideation_active, plan_or_imminent}`,
  `subject ∈ {self, other, abstract}`, `confidence ∈ [0,1]`;
- модель: **GigaChat-2 Lite**, `temperature=0`, ~375–400 мс, `max_tokens≈500`;
- сбой API → «недоступен» (не `none`); нераспарсенный ответ → `distress` (не `none`).

Бенч (`safety-bench/docs/01_report.md`, test split): recall 0.81 на `{ideation_active,
plan_or_imminent}`, FPR 0.06 на hard-negative, subject-accuracy 0.96.

---

## 2. Где встраивается

`app/llm/pipeline/stages/boundary_guard.py`, ровно в тот слот, где был `crisis_semantic`
(после L0-`urgent`-проверки). Условия вызова:

```
L0 дал safety_level == "urgent"      → early_response уже стоит, классификатор НЕ зовём
prompt-injection сработал            → early_response уже стоит, НЕ зовём
L0 intent ∈ {data_entry}             → НЕ зовём (числовая запись, «давление 125/85»)
                                        NB: «давление 200/100, не хочу жить» L0 ловит как
                                        urgent раньше — сюда не дойдёт
иначе                                → зовём safety_classifier.classify(user_input, context=[])
```

Позиция в стадии: **после** обеих prompt-injection проверок (инъекционный текст не должен
стоить LLM-вызова), но до выхода из стадии.

## 3. Что делает каждый уровень (решения Дмитрия, 2026-08-31)

Паттерн — как у OpenAI/Anthropic: модель **отвечает по существу**, а мягкая
плашка с ресурсами добавляется **в конец**; жёсткий обрыв — только для самого
близкого к действию уровня.

| level + subject | Действие | Механизм |
|---|---|---|
| `plan_or_imminent` + `self` | **Обрыв до генерации.** `early_response` = кризис-текст (§3a), `early_response_source = "boundary_guard_safety_llm"` | как L0-urgent |
| `ideation_active` + `self` | **[открытый вопрос, §6.1]** либо обрыв (как plan), либо: агент отвечает + **обязательная** плашка в конце | `context.safety_footer` |
| `ideation_passive` + `self` | Агент отвечает штатно + **мягкая** плашка в конце (§3b). Тир → PRO | `context.safety_footer` + `concern` |
| `distress` + `self` | Агент отвечает. В промпт агента — подсказка «человеку сейчас тяжело, бережнее». Плашки нет | `supervisor_state` hint |
| любой + `other` / `abstract` | Ничего (заметка в диагностику) | — |
| `none` | Ничего | — |
| сбой API / нераспарсено | Ничего — работаем как L0-only. WARNING в лог + диагностику. (Нераспарсенный ответ модели → трактуем как `distress`, не `none`) | fail-open |

### 3a. Кризис-текст для обрыва (`plan_or_imminent`, и `ideation_active` если §6.1 = обрыв)

Текущий `CRISIS_RESPONSE` уже тёплый — оставляем его же (тексты обязаны совпадать
с `_apply_agent_safety_net`, см. `safety_responses.py`). При желании — чуть смягчить
первую строку, но это отдельная правка `safety_responses.py`, влияет на оба эшелона.

### 3b. Плашка в конец (`context.safety_footer`)

Новое поле `PipelineContext.safety_footer: str | None`. Ставит `boundary_guard`,
дописывает `supervisor` **после** `context.response_draft` (до сборки `LLMResponse`).
Черновик текста (согласовать):

> `\n\n—\nЕсли станет совсем тяжело, телефон доверия 8-800-2000-122 работает круглосуточно и бесплатно. Я тоже рядом — пиши.`

Для `ideation_active` (если не обрыв) — жёстче:

> `\n\n—\nТо, о чём ты пишешь, — серьёзно. Пожалуйста, позвони на телефон доверия 8-800-2000-122 (бесплатно, круглосуточно) или скажи близкому, что тебе нужна поддержка. Я рядом, но живой человек сейчас важнее.`

Диагностика: `context.diagnostics["boundary_guard"] = {type: "safety_llm", level,
subject, confidence, latency_ms, action: "interrupt"|"footer"|"hint"|"none"}`.

## 4. Код

**`app/llm/safety_classifier.py`** (новый):
- `class SuicideRisk(BaseModel)`: `level: Literal[...]`, `subject: Literal[...]`, `confidence: float`
- `@dataclass SafetyAssessment`: то же + `latency_ms`, `available: bool`
- `async def classify(text, context=None) -> SafetyAssessment`:
  - `client = await pool.get_available("lite")`
  - `client.structured(messages, system_prompt=_PROMPT, schema=SuicideRisk, temperature=0.0,
    step="safety_classifier", patient_id=..., session_id="safety-classifier-shared",
    max_tokens=500)` — общий `session_id` (рубрика константна → префиксный кэш)
  - любой `LLMError` / таймаут → `SafetyAssessment(available=False)`, не пробрасываем
- `_PROMPT` читается из `app/llm/prompts/safety_classifier.txt` при импорте

**`boundary_guard.py`:** заменить комментарий-заглушку на ветку из §2–§3.
`_LLM_SAFETY_ENABLED` — флаг `LLM_SAFETY_LLM` в `.env.example` (default `false`,
включаем после staging-smoke — как и планировалось для crisis_semantic, но теперь
оффлайн-цифры включение оправдывают).

**`app/llm/pipeline/stages/classification.py`:** уже читает `l0.safety_level == "concern"`
→ PRO. Если `ideation_passive` поднимает `concern`, надо чтобы boundary_guard положил это
туда, откуда classification возьмёт (сейчас `context.l0` — можно доложить в объект решения
или отдельным полем `context.safety_concern`).

## 5. Тесты

1. **Юнит** (`tests_py/llm/test_safety_classifier.py`): мок `pool.get_available` →
   каждый из 5 уровней × subject → корректный `early_response` / тир / диагностика;
   сбой API → `available=False`, pipeline не падает; нераспарсенный JSON → `distress`.
2. **Golden-регрессия** (`tests_py/llm/test_safety_classifier_golden.py`, `@pytest.mark.skipif`
   без `GIGACHAT_KEY_A1`): прогон против `tests/fixtures/safety_golden.jsonl` **dev split**,
   ассерты `recall({act,plan}/self) ≥ 0.75` и `FPR(none/self) ≤ 0.12` — ловит регрессии
   рубрики. Test split НЕ трогаем (чтобы не подгонять — как в safety-bench).
3. **patient-sim** (`--personas p01,p02,p03 --no-judge`): s01/s02 по-прежнему обрываются
   (теперь через L0 ИЛИ классификатор), s03 (давление/вода) без ложного кризиса.
4. **Латентность**: залогировать `latency_ms` из первых прогонов, свериться с бюджетом hot-path.

## 6. Открытые вопросы

### Решено (Дмитрий, 2026-08-31)

- **§3 ответы** — модель отвечает + мягкая плашка в конец, обрыв только для самого
  острого уровня (см. §3).
- **Текст обрыва** — тот же `CRISIS_RESPONSE` (§3a).
- **Контекст** — тянем предыдущую реплику(и) бота из `llm.chat_messages` через
  `request.db`; `db=None` (patient-sim) → без контекста, не падаем.
- **Флаг** — `LLM_SAFETY_LLM` default **ON** на dev. Держим как kill-switch,
  снимаем после живой проверки (как `2316a40`).
- **Проактивный контур** — классификатор **реактивный, только `boundary_guard`**
  (объяснение — §6.2).

### 6.1. Осталось решить: где проходит линия жёсткого обрыва?

`ideation_active` (+self) = «хочу себя убить», «думаю покончить с собой», «всё чаще
мысли что-то с собой сделать» — способ/время НЕ названы.

- **Вариант A (консервативный):** `ideation_active` → обрыв, как `plan_or_imminent`.
  Совпадает с recall-точкой safety-bench 0.81 (там метрика по `{active, plan}`).
  Риск: чат-бот вообще не отвечает по существу на прямое «хочу себя убить», сразу протокол.
- **Вариант B (по образцу OpenAI/Anthropic):** `ideation_active` → агент отвечает
  бережно по существу + **жёсткая обязательная плашка** (§3b, второй текст). Обрыв
  только на `plan_or_imminent`. Менее «обрывающе», но чат-бот ведёт разговор там,
  где человек прямо говорит о суициде без плана.
- Граница `active`/`plan` в реальных сообщениях размытая — это цена варианта B.

### 6.2. Пояснение про проактивный контур

Два контура (см. `ROADMAP_AGENT.md`):
- **Реактивный** — пациент пишет сообщение → пайплайн из 5 стадий → `boundary_guard`
  читает **текст пациента**. Классификатор живёт здесь.
- **Проактивный** — систему инициирует сама (утренний дайджест, «3 дня не отмечал
  сон», разбор недели, нуджи по аномалиям). Генерит `proactive_coordinator` /
  `morning_service` по **структурным трекерным данным** (АД, вес, часы сна,
  приверженность), **свободного текста пациента в этот момент нет** — классифицировать
  нечего.

→ Прогонять проактив через классификатор незачем. **Отдельный, не входит сюда:**
«проактив приглушается, если недавно был кризисный сигнал» (сегодняшний нудж «отметь
вес!» после вчерашнего «устал бороться, зачем продолжать» — бестактен). Это фича
crisis-aware gating проактива, свой дизайн.

### 6.3. Латентность (Дмитрий: «надо подумать»)

+1 вызов GigaChat-2 Lite (~375–400 мс) до генерации, на каждом сообщении, где L0
не дал urgent. Concurrency=1, один живой диалог — по `SPRINT1_INVESTIGATIONS.md` #1
хватает. Варианты:

- **A. Серийно в `boundary_guard`** (просто): +~400 мс к первому байту ответа.
- **B. Параллельно со стадией `classification`** (L1/L2 роутер тоже ходит в
  embeddings/LLM): `boundary_guard` стартует задачу, `classification` крутится
  рядом, чекпойнт перед `supervisor` дожидается вердикта. Экономит ~200–400 мс
  wall-time. Ломает «стадия завершается до следующей» — задачу надо протащить
  через `context`.
- **C. Гибрид:** `plan_or_imminent` ловим до генерации (обрыв), для остального
  вердикт приезжает во время генерации и правит `_apply_agent_safety_net` пост-фактум
  (как сейчас с самооценкой агента). Latency 0, но на `plan` мы всё равно сделали
  Pro/Max-вызов и выкинули текст.

Рекомендация: **A** для v1 (проще, безопаснее), замер `latency_ms` на первых
прогонах, **B** если 400 мс на практике мешает.

## 7. Оценка

- `safety_classifier.py` + промпт + ветка в boundary_guard: ~0.5 дня
- Тесты (юнит + golden-регрессия + patient-sim прогон): ~0.5 дня
- Итого ~1 день + staging-smoke перед снятием флага.

## 8. Не входит

- Правка L0 regex — **сделана отдельно 2026-08-31** (recall на golden test 43% → 68%,
  FP не вырос). Классификатор строится поверх этого L0.
- Дообучение/свои эмбеддинги — отклонено (safety-bench + `CRISIS_SEMANTIC_VALIDATION.md`).
