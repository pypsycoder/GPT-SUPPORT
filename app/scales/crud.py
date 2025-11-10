from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from app.scales.models import ScaleDraft, ScaleResponse
from core.db.session import async_session_factory


# ✅ Получить или создать черновик прохождения шкалы
async def get_or_create_draft(user_id: int, scale_code: str, version: str, session: AsyncSession):
    result = await session.execute(
        select(ScaleDraft).where(
            ScaleDraft.user_id == user_id,
            ScaleDraft.scale_code == scale_code
        )
    )
    draft = result.scalars().first()

    if draft:
        return {
            "id": draft.id,
            "current_index": draft.current_index,
            "answers": draft.answers,
        }

    new_draft = ScaleDraft(
        user_id=user_id,
        scale_code=scale_code,
        current_index=0,
        answers={},
        started_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    session.add(new_draft)
    await session.commit()
    await session.refresh(new_draft)

    return {
        "id": new_draft.id,
        "current_index": new_draft.current_index,
        "answers": new_draft.answers,
    }

# ✏️ Обновить черновик: текущий вопрос и ответ
async def update_draft_answer(draft_id: int, question_id: str, answer_value: int):
    async with async_session_factory() as session:
        result = await session.execute(
            select(ScaleDraft).where(ScaleDraft.id == draft_id)
        )
        draft = result.scalar_one_or_none()
        if draft:
            draft.answers = draft.answers or {}
            draft.answers[question_id] = answer_value
            draft.current_index += 1
            draft.updated_at = datetime.utcnow()
            await session.commit()

# 🧹 Удалить черновик после завершения
async def delete_draft(draft_id: int):
    async with async_session_factory() as session:
        await session.execute(
            delete(ScaleDraft).where(ScaleDraft.id == draft_id)
        )
        await session.commit()

# ✅ Сохранить финальный результат в responses
async def finalize_response(user_id: str, schema: dict, answers: dict):
    # Подсчёт результатов по шкалам A / D
    scores = {"A": 0, "D": 0}
    for item in schema["items"]:
        qid = item["id"]
        scale = item["scale"]
        scores[scale] += answers.get(qid, 0)

    # Интерпретация
    interpretation = {}
    for scale_key, score in scores.items():
        cuts = schema["output"][scale_key]["cutoffs"]
        texts = schema["output"][scale_key]["interpretation"]
        if score <= cuts[0]:
            interpretation[scale_key] = texts[0]
        elif score <= cuts[1]:
            interpretation[scale_key] = texts[1]
        else:
            interpretation[scale_key] = texts[2]

    async with async_session_factory() as session:
        result = ScaleResponse(
            user_id=int(user_id),
            scale_code=schema["code"],
            version=schema.get("version", "1.0"),
            completed_at=datetime.utcnow(),
            raw_answers=answers,
            result=scores,
            interpretation=", ".join(f"{k}: {v}" for k, v in interpretation.items())
        )
        session.add(result)
        await session.commit()
