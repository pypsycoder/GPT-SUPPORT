# Memory Schema

## Purpose

This file defines the first working contract for memory in the LLM system.

We separate:

- `MemoryCandidate`
- `MemoryWriteDecision`
- `STMemoryEntry`
- `LTMemoryEntry`

The goal is to make memory writes explicit, reviewable, and conservative.

## Principles

- Specialists do not write memory directly.
- Composer does not write memory directly.
- Final response text is not memory.
- Everything starts as a candidate.
- `ST-memory` is easier to write to.
- `LT-memory` requires stronger evidence.

## 1. MemoryCandidate

This is the raw structured signal produced by some part of the system.

```json
{
  "candidate_id": "cand_001",
  "source_layer": "clarifier",
  "memory_scope": "st",
  "candidate_type": "current_intent",
  "key": "current_intent",
  "value": "practical_day_support",
  "evidence": [
    "user said: help me get through today"
  ],
  "confidence": 0.92,
  "session_id": "sess_123",
  "patient_id": 1,
  "created_at": "2026-04-07T12:00:00Z"
}
```

### Fields

- `candidate_id`
  unique candidate id

- `source_layer`
  where the candidate came from
  values:
  `clarifier | router | progress | content_selector | mixed_flow | system`

- `memory_scope`
  proposed target scope
  values:
  `st | lt | undecided`

- `candidate_type`
  semantic type

- `key`
  normalized field name

- `value`
  normalized structured value

- `evidence`
  short evidence snippets or structured facts

- `confidence`
  optional local confidence for the candidate producer
  this is not final write permission

- `session_id`
  current session id

- `patient_id`
  patient id

- `created_at`
  timestamp

## 2. MemoryWriteDecision

This is the output of the memory writer / memory gate.

```json
{
  "candidate_id": "cand_001",
  "decision": "write",
  "target_memory": "st",
  "reason": "session_context_needed",
  "ttl_seconds": 7200,
  "merge_strategy": "replace_by_key",
  "review_needed": false
}
```

### Fields

- `candidate_id`
  the candidate being evaluated

- `decision`
  values:
  `write | reject | defer`

- `target_memory`
  values:
  `st | lt | none`

- `reason`
  write or reject reason

- `ttl_seconds`
  for `ST-memory`

- `merge_strategy`
  values:
  `replace_by_key | append | increment_evidence | keep_existing`

- `review_needed`
  whether this should be reviewed by a stricter LT policy

## 3. STMemoryEntry

Short-term memory entry for the current session or current thread.

```json
{
  "memory_id": "st_001",
  "patient_id": 1,
  "session_id": "sess_123",
  "thread_id": "thread_help_sleep",
  "key": "current_problem",
  "value": "low_energy_today",
  "source_layer": "clarifier",
  "evidence": [
    "user said they feel drained today"
  ],
  "created_at": "2026-04-07T12:00:00Z",
  "updated_at": "2026-04-07T12:01:00Z",
  "expires_at": "2026-04-07T14:00:00Z",
  "status": "active"
}
```

### Typical ST keys

- `current_problem`
- `current_intent`
- `context_fact`
- `active_flow`
- `active_help_mode`
- `clarifier_question_asked`
- `clarifier_answer`
- `open_subtask`
- `user_constraint_for_this_session`

### ST rules

- scoped to session or thread
- easier to overwrite
- can expire automatically
- should support quick read before routing

## 4. LTMemoryEntry

Long-term memory entry for stable patient-level knowledge.

```json
{
  "memory_id": "lt_001",
  "patient_id": 1,
  "key": "response_style_preference",
  "value": "short_practical_answers",
  "source_policy": "explicit_user_preference",
  "evidence_count": 2,
  "evidence_examples": [
    "user said: keep it short and practical",
    "user rejected long explanations"
  ],
  "created_at": "2026-04-07T12:00:00Z",
  "updated_at": "2026-04-10T09:30:00Z",
  "status": "active"
}
```

### Typical LT keys

- `response_style_preference`
- `content_preference`
- `repeated_problem_pattern`
- `repeated_trigger`
- `support_mode_preference`
- `stable_progress_fact`

### LT rules

- patient-level, not session-level
- updated rarely
- requires evidence or explicit signal
- should support merge and decay

## 5. Allowed Source Layers

### Can propose ST candidates

- `clarifier`
- `router`
- `mixed_flow`
- `content_selector`
- `progress`

### Can propose LT candidates

- `progress`
- `content_selector`
- `system`
- `clarifier` only when the user explicitly states a stable preference

### Cannot write memory directly

- `psych_support`
- `routine`
- `education`
- `composer`
- `critic`

## 6. Candidate Types

Suggested first version:

- `current_problem`
- `current_intent`
- `context_fact`
- `active_flow`
- `active_help_mode`
- `clarifier_state`
- `session_constraint`
- `explicit_user_preference`
- `repeated_behavior_signal`
- `progress_event`

## 7. LT Write Policies

Allowed LT write policies:

- `explicit_user_preference`
- `repeated_pattern`
- `progress_event`
- `stable_behavior_signal`

If a candidate does not match one of these, it should not be written to LT.

## 8. Example Decisions

### Example A: ST-only

User says:
"No lesson now, just help me get through today."

Candidate:

```json
{
  "source_layer": "clarifier",
  "candidate_type": "session_constraint",
  "key": "user_constraint_for_this_session",
  "value": "no_lesson_now"
}
```

Decision:

```json
{
  "decision": "write",
  "target_memory": "st",
  "reason": "session_context_needed",
  "ttl_seconds": 7200
}
```

### Example B: LT write

User repeatedly prefers short practical answers across sessions.

Candidate:

```json
{
  "source_layer": "system",
  "candidate_type": "stable_behavior_signal",
  "key": "response_style_preference",
  "value": "short_practical_answers"
}
```

Decision:

```json
{
  "decision": "write",
  "target_memory": "lt",
  "reason": "repeated_pattern_confirmed",
  "merge_strategy": "replace_by_key",
  "review_needed": false
}
```

## 9. First Implementation Constraint

For the first version:

- keep `ST-memory` simple and operational
- keep `LT-memory` small and conservative
- reject most LT candidates by default

If there is uncertainty:

- write to `ST`
- do not write to `LT`
