# Emotional Expert Handoff Design

## Goal
After the router returns:
- `Следующее действие: делегировать`
- `Подключаемые эксперты: ...`

the graph must actually continue into an expert node instead of jumping straight to final rewrite.

## Current Problem
Right now delegation is only declarative:
- the router selects `эмоциональная_поддержка`
- the state/trace show that delegation happened
- but no expert node is executed
- the final reply is still written by the generic supervisor rewrite layer

Because of this, turn 3 answers look like generic support text, not like targeted expert help.

## First Scope
Implement real handoff only for one expert:
- `эмоциональная_поддержка`

No parallel experts yet.
No merge logic yet.
No multi-expert synthesis yet.

## Graph Flow

### 1. Router Analysis
Already exists.

Returns router card:
- `Проблема`
- `Контекст`
- `Намерение`
- `Фаза`
- `Статус`
- `Нужны уточнения`
- `Нужен еще цикл`
- `Следующее действие`
- `Подключаемые эксперты`
- `Обоснование`

### 2. Router Card Validation
Already exists.

Checks:
- required fields
- dictionary values
- consistency
- expert presence for `делегировать`

### 3. Execute Router Decision
If:
- `уточнить` -> ask user question
- `завершить` -> short local reply
- `делегировать` -> continue into real expert flow

### 4. Prepare Expert Tasks
Input:
- router card
- current dialog state

Output:
- list of expert tasks

Each expert task contains:
- `эксперт`
- `проблема`
- `контекст`
- `намерение`
- `задача`

### 5. Invoke Emotional Expert
Input:
- `Проблема`
- `Контекст`
- `Намерение`
- `Задача`

The expert must not:
- reroute
- choose another expert
- rewrite the whole conversation
- ignore the assigned task

The expert must:
- provide specialized emotional support
- help first
- only then ask a follow-up if it is still useful

### 6. Collect Expert Result
For the first version:
- if there is one expert, just carry its result forward

Later this node can merge multiple expert outputs.

### 7. Final Synthesis
The final writer receives:
- router card
- expert result

The final writer must:
- preserve expert meaning
- smooth phrasing
- remove repetition
- avoid inventing new help outside expert output

The final writer is a formatter, not a hidden expert.

## Emotional Expert Input Contract

The node receives:
- `Проблема`
- `Контекст`
- `Намерение`
- `Задача`

These values come from the router card and expert task packet.

## Emotional Expert Output Contract

The expert returns:
- `Поддержка`
- `Шаг сейчас`
- `Уточнение после помощи`
- `Нужно ли уточнение`
- `Обоснование`

### Meaning of Fields

#### `Поддержка`
- one short validating phrase
- not a long intro
- not a generic lecture

#### `Шаг сейчас`
- one concrete, safe action for the current moment
- not a long checklist

#### `Уточнение после помощи`
- one soft follow-up question
- only after support
- may be `нет`

#### `Нужно ли уточнение`
- `да`
- `нет`

#### `Обоснование`
- one short debug-facing explanation

## Behavioral Rule
The emotional expert should follow:

1. support first
2. one practical next step
3. only then optional clarification

It should not respond with only:
- `Что именно тебя пугает?`

if there is already enough context to help in the moment.

## Expected Effect
This change will make delegation real:
- `делегировать` will trigger an actual expert node
- turn 3 responses will stop sounding like generic supervisor text
- expert quality can be tuned independently from router quality

## State to Preserve
After expert execution, store:
- last router card
- invoked expert name
- expert output
- whether a follow-up question was produced
- whether another cycle is needed

## First Version Boundaries
Version 1 should stay small:
- one expert only: `эмоциональная_поддержка`
- one expert task only
- one expert output card only
- no parallelism
- no complex merge layer

This is enough to turn router delegation into a real graph handoff.
