"""Questionnaire engine service.

Contains business logic for running questionnaire workflows without
any coupling to Telegram or other presentation layers.
"""

from app.scales.crud import (
    delete_draft,
    finalize_response,
    get_or_create_draft,
    update_draft_answer,
)


async def start_questionnaire_for_user(session, user, schema: dict) -> dict:
    """Create or fetch a questionnaire draft for a user.

    Returns the draft id, current question index, existing answers and
    the schema itself so the caller can continue the flow.
    """

    draft = await get_or_create_draft(user.id, schema["code"], schema["version"], session)

    return {
        "draft_id": draft["id"],
        "current_index": draft["current_index"],
        "answers": draft["answers"],
        "schema": schema,
    }


async def process_answer(
    session,
    draft_id: int,
    user_id: int,
    schema: dict,
    answers: dict[str, int],
    current_index: int,
    selected_value: int,
) -> dict:
    """Handle answer selection and return next step info or final result."""

    items = schema.get("items", [])
    item = items[current_index]

    answers[item["id"]] = selected_value

    await update_draft_answer(draft_id, item["id"], selected_value)

    next_index = current_index + 1
    if next_index < len(items):
        return {
            "finished": False,
            "next_index": next_index,
            "next_item": items[next_index],
            "answers": answers,
        }

    result = build_result(schema, answers)
    await finalize_response(user_id, schema, answers)
    await delete_draft(draft_id)

    return {
        "finished": True,
        "result": result,
        "answers": answers,
    }


def compute_scores(schema: dict, answers: dict[str, int]) -> dict[str, int]:
    """Compute scale scores (e.g., A and D) based on provided answers."""

    scores: dict[str, int] = {}
    for item in schema.get("items", []):
        item_id = item.get("id")
        scale_code = item.get("scale")
        if not scale_code:
            continue
        value = answers.get(item_id)
        if value is None:
            continue
        scores[scale_code] = scores.get(scale_code, 0) + int(value)

    return scores


def interpret_scores(schema: dict, scores: dict[str, int]) -> list[str]:
    """Generate human-readable interpretations for computed scores."""

    lines: list[str] = []
    output_cfg = schema.get("output", {})

    for scale_code, total in scores.items():
        cfg = output_cfg.get(scale_code)
        if not cfg:
            continue

        name = cfg.get("name", scale_code)
        cutoffs = cfg.get("cutoffs", [])
        labels = cfg.get("interpretation", [])

        if len(cutoffs) == 2 and len(labels) >= 3:
            if total < cutoffs[0]:
                level = labels[0]
            elif total < cutoffs[1]:
                level = labels[1]
            else:
                level = labels[2]
        elif len(cutoffs) == 1 and len(labels) >= 2:
            if total < cutoffs[0]:
                level = labels[0]
            else:
                level = labels[1]
        else:
            level = labels[0] if labels else "без интерпретации"

        lines.append(f"{name}: {total} баллов — {level}")

    return lines


def build_result(schema: dict, answers: dict[str, int]) -> dict:
    """Wrapper that prepares scores and interpretation lines."""

    scores = compute_scores(schema, answers)
    lines = interpret_scores(schema, scores)

    return {
        "scores": scores,
        "lines": lines,
    }

