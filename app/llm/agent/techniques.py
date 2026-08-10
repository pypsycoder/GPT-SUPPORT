"""Инжектор библиотеки техник для одноагентной ветки.

Существующие ``format_*`` из ``technique_library`` говорят на языке старой
карточки («поле Шаг сейчас», «Режим интервенция») — агенту они не подходят.
Здесь тот же отбор техник, но формулировки под схему ``AgentReply``.

Три состояния, как и в старой ветке:
  1. активна интерактивная техника и шаги не кончились — выдаём текущий шаг;
  2. шаги кончились — просим спросить о результате;
  3. иначе — список кандидатов, из которых агент выбирает один.

Отбор эмоций и возбуждения — детерминированный, без вызова LLM: те же
``infer_emotions`` / ``infer_arousal``, что и у старой ветки, чтобы сравнение
двух веток шло на одинаковых входных данных.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from app.llm.technique_library import (
    TechniqueCard,
    get_technique_by_id,
    get_techniques,
    infer_arousal,
    infer_emotions,
)

logger = logging.getLogger("gpt-support-llm.agent.techniques")

NO_TECHNIQUE = "нет"

# Сколько последних техник не предлагать повторно.
_RECENT_WINDOW = 5


@dataclass(slots=True)
class TechniqueState:
    """Прогресс по технике внутри треда."""

    current_id: str | None = None
    step_index: int = 0
    turns: int = 0
    recent_ids: list[str] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.recent_ids is None:
            self.recent_ids = []


def _render_step(card: TechniqueCard, step_idx: int) -> str:
    total = len(card.steps)
    return (
        f"АКТИВНАЯ ТЕХНИКА [{card.id}] «{card.name}», шаг {step_idx + 1} из {total}.\n"
        f"Передай пациенту ИМЕННО этот шаг, своими словами по тону, но не меняя сути:\n"
        f"«{card.steps[step_idx]}»\n"
        f"В поле technique_id укажи {card.id} — иначе прогресс не сохранится.\n"
        f"Не предлагай другую технику, пока эта не закончена."
    )


def _render_completion(card: TechniqueCard) -> str:
    prompt = card.completion_prompt or "Что заметил? Что почувствовал после?"
    intent = f"Зачем она была нужна: {card.therapeutic_intent}\n" if card.therapeutic_intent else ""
    return (
        f"ТЕХНИКА [{card.id}] «{card.name}» ПРОЙДЕНА ЦЕЛИКОМ.\n"
        f"{intent}"
        f"Если пациент уже сказал, как ему после неё — отреагируй на это и реши, "
        f"продолжать или переходить к другому.\n"
        f"Если не сказал — спроси: «{prompt}»\n"
        f"Новую технику сейчас не предлагай. В technique_id укажи {NO_TECHNIQUE}."
    )


def _render_candidates(cards: list[TechniqueCard], current_id: str | None) -> str:
    lines = [
        "Подходящие техники. Если уместен практический шаг — возьми ОДНУ из них "
        "и передай её пациенту, а её id укажи в поле technique_id. "
        "Если человеку сейчас нужно просто быть услышанным — техника не обязательна, "
        f"тогда technique_id = {NO_TECHNIQUE}."
    ]
    for card in cards:
        mark = " (уже начата)" if card.id == current_id else ""
        lines.append(f"[{card.id}] {card.name}{mark} — {card.mechanism}")
        if card.steps:
            if card.interactive:
                lines.append(f"  Первый шаг, передай дословно: «{card.steps[0]}»")
            else:
                for index, step in enumerate(card.steps, start=1):
                    lines.append(f"  {index}. {step}")
    return "\n".join(lines)


def build_technique_block(
    *,
    user_message: str,
    context: str = "",
    state: TechniqueState | None = None,
) -> str:
    """Блок техник для волатильного слоя агента. Пустая строка — если техник нет."""
    state = state or TechniqueState()
    current_id = str(state.current_id or "").strip() or None

    if current_id:
        card = get_technique_by_id(current_id)
        if card and card.interactive and card.steps:
            if state.step_index < len(card.steps):
                return _render_step(card, state.step_index)
            return _render_completion(card)

    emotions = infer_emotions(user_message, context)
    arousal = infer_arousal(user_message, context)
    if not emotions:
        # get_techniques на пустом наборе эмоций отдаёт дефолтную тройку, поэтому
        # без этой проверки блок уезжал бы даже в «спасибо» и «привет»: лишние
        # ~600 токенов на ход и соблазн предложить упражнение там, где не просили.
        logger.debug("[agent.techniques] эмоций не найдено — блок техник не инжектим")
        return ""
    # Последнюю технику из недавних оставляем в списке: она может быть текущей.
    recent = list(state.recent_ids or [])
    exclude_ids = recent[:-1] if len(recent) > 1 else []
    cards = get_techniques(emotions, arousal, exclude_ids=exclude_ids)
    logger.debug(
        "[agent.techniques] emotions=%s arousal=%s exclude=%s found=%s",
        emotions, arousal, exclude_ids, [c.id for c in cards],
    )
    if not cards:
        return ""
    return _render_candidates(cards, current_id)


def advance(state: TechniqueState, technique_id: str | None) -> TechniqueState:
    """Новое состояние прогресса после ответа агента.

    В отличие от старой ветки прогресс считается по явному полю схемы, а не по
    префиксу ``[pNN]``, выковырянному из текста, — поэтому шаг не застревает.
    """
    chosen = str(technique_id or "").strip()
    if not chosen or chosen.lower() == NO_TECHNIQUE:
        # Техника не выдавалась: прогресс сохраняем как есть.
        return state

    card = get_technique_by_id(chosen)
    if card is None:
        logger.debug("[agent.techniques] неизвестный technique_id=%r, игнорирую", chosen)
        return state

    recent = list(state.recent_ids or [])
    if not recent or recent[-1] != chosen:
        recent.append(chosen)

    if chosen != state.current_id:
        step_index = 1 if (card.interactive and card.steps) else 0
        return TechniqueState(
            current_id=chosen, step_index=step_index, turns=1, recent_ids=recent[-_RECENT_WINDOW:]
        )

    step_index = state.step_index
    if card.interactive and card.steps:
        step_index = min(state.step_index + 1, len(card.steps))
    return TechniqueState(
        current_id=chosen,
        step_index=step_index,
        turns=int(state.turns or 0) + 1,
        recent_ids=recent[-_RECENT_WINDOW:],
    )
