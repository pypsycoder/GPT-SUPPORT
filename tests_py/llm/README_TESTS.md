# LLM Tests

## Current Test Groups

### Stateful Supervisor Path
- `test_pipeline.py` - current pipeline integration for the stateful supervisor MVP
- `test_supervisor_models.py` - JSON-friendly state models and roundtrip serialization
- `test_short_answers.py` - short-answer normalization and pending-question parsing
- `test_state_merge.py` - incremental state updates via `merge_state_delta()`
- `test_supervisor_classification.py` - rule-based `domain` / `intent` / `message_type`
- `test_supervisor_gate.py` - clarify-before-delegate behavior
- `test_supervisor.py` - compatibility smoke tests for supervisor exports

### Infrastructure / Supporting Modules
- `test_context_optimization.py` - caching and optimization behavior
- `test_resilience.py` - circuit breaker, retry, and resilient client behavior
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
pytest tests_py/llm/test_pipeline.py tests_py/llm/test_supervisor_models.py tests_py/llm/test_short_answers.py tests_py/llm/test_state_merge.py tests_py/llm/test_supervisor_classification.py tests_py/llm/test_supervisor_gate.py tests_py/llm/test_supervisor.py -q
```
