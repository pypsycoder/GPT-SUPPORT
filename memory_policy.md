# Memory Policy

## Purpose

This file defines when memory should be read, when it should be written, and who is responsible.

## 1. Read Policy

### Read ST-memory

Read `ST-memory`:

- after safety screening
- before message decomposition
- before clarifier
- before handling short follow-up replies
- before repeating retrieval in the same thread

Use `ST-memory` for:

- current branch continuity
- current problem / intent / context
- unresolved tasks
- clarifier state

### Read LT-memory

Read `LT-memory`:

- after safety screening
- before final route selection
- before content recommendation
- before CTA selection

Use `LT-memory` for:

- stable patient preferences
- repeated patterns
- long-term support mode tendencies
- stable progress facts

Do not use `LT-memory` to override the fresh request.

## 2. Write Policy

### ST-memory writes

Write to `ST-memory` after:

- message decomposition
- clarifier question
- clarifier answer
- help mode selection
- mixed-flow split
- route selection

### LT-memory writes

Write to `LT-memory` only if at least one is true:

- explicit user preference
- repeated pattern across sessions
- reliable progress event
- stable behavior signal that changes routing or content choice

## 3. Responsibility

### Candidate producers

- `clarifier`
- `router`
- `mixed_flow`
- `progress layer`
- `content selector`
- `system aggregation layer`

### Memory writer

The memory writer decides:

- whether to write
- where to write
- whether to merge or replace
- whether the signal is strong enough for LT

### Memory store

The memory store handles:

- persistence
- expiration
- deduplication
- merge behavior

## 4. Forbidden Direct Writers

These layers must not write memory directly:

- `psych_support`
- `routine`
- `education`
- `composer`
- `critic`

Reason:

they are too local, too prompt-dependent, and too sensitive to noisy retrieval.

## 5. Event Policy Table

| Event | ST | LT | Rule |
|---|---|---|---|
| Current intent identified | Yes | No | session-only |
| Current problem identified | Yes | No | session-only |
| Clarifier answer received | Yes | No | session-only |
| User says “not after dialysis” | Yes | No | branch context |
| User says “keep it short and practical” | Yes | Yes | explicit preference |
| One-time refusal of lesson | Yes | No | not stable enough |
| Repeated refusal of lessons across sessions | Yes | Yes | repeated pattern |
| Lesson passed | Yes | Yes | reliable progress fact |
| One practice completed | Yes | No | not enough for LT preference |
| Repeated practice-first choice | Yes | Yes | stable behavior signal |
| Specialist output generated | No | No | forbidden direct write |
| Composer output generated | No | No | forbidden direct write |
| Critic found a quality issue | No | No | telemetry only |

## 6. Conservative Default

When unsure:

- write to `ST`
- do not write to `LT`

This is the default safety rule for memory quality.
