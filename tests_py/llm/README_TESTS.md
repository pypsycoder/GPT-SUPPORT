# LLM Tests

## Current Test Groups

### Stateful Supervisor Path
- `test_pipeline.py` - current pipeline integration for the stateful supervisor MVP
- `test_supervisor_models.py` - JSON-friendly state models and roundtrip serialization
- `test_short_answers.py` - short-answer normalization and pending-question parsing
- `test_state_merge.py` - incremental state updates via `merge_state_delta()`
- `test_supervisor_classification.py` - rule-based `domain` / `intent` / `message_type`
- `test_supervisor_gate.py` - clarify-before-delegate behavior
- `test_expert_selection.py` - deterministic expert routing
- `test_synthesizer.py` - response assembly order and deduplication
- `test_supervisor.py` - compatibility smoke tests for supervisor exports

### Transitional Legacy-Backed Tests
- `test_intake.py` - keep for now because `app.llm.intake` is still imported by active code
- `test_orchestration.py` - keep for now because `app.llm.orchestration` is still imported by active code
- `test_prompt_policy.py` - keep for now because prompt loading from the legacy path is still used
- `tests_py/researchers/test_chat_debug.py` - keep because the live researcher debug route still exercises legacy-backed flow

These tests stay until active callers migrate off the monolithic generator path:
- `app/routers/chat.py`
- `app/researchers/router.py`
- any remaining proactive or diagnostic flows still importing `app.llm.agent.generate_response()`

### Infrastructure / Supporting Modules
- `test_context_builder.py` - context bundle assembly
- `test_context_optimization.py` - caching and optimization behavior
- `test_resilience.py` - circuit breaker, retry, and resilient client behavior
- `test_response_validator.py` - validation and rewrite trigger logic
- `test_memory_session.py` - ST session memory behavior
- `test_memory_writer.py` - memory candidate filtering and write decisions
- `test_eval_detection.py` - eval detection
- `test_eval_report.py` - eval report rendering
- `test_http_policy.py` - HTTP retry policy
- `test_morning_service.py` - morning message logic
- `test_parser.py` - parser helpers
- `test_rag_indexer.py` - RAG indexing helpers
- `test_rag_retriever.py` - retrieval helpers
- `test_worker.py` - worker helpers

## Cleanup Rule

Remove a test when it targets:
- an unused entrypoint
- an archived artifact
- a path that is no longer imported or mounted

Keep a test when it protects:
- a currently imported module
- a currently mounted route
- a compatibility surface that is still exercised in production

## Recommended Commands

Run the full LLM test suite:

```bash
pytest tests_py/llm -q
```

Run the researcher debug route coverage:

```bash
pytest tests_py/researchers/test_chat_debug.py -q
```

Run the current stateful supervisor MVP subset:

```bash
pytest tests_py/llm/test_pipeline.py tests_py/llm/test_supervisor_models.py tests_py/llm/test_short_answers.py tests_py/llm/test_state_merge.py tests_py/llm/test_supervisor_classification.py tests_py/llm/test_supervisor_gate.py tests_py/llm/test_expert_selection.py tests_py/llm/test_synthesizer.py tests_py/llm/test_supervisor.py -q
```
