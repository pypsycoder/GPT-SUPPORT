"""Prompting, parsing, and validation helpers for Graph v2."""

from __future__ import annotations

from typing import Any

from app.llm.errors import LLMConfigurationError
from app.llm.langgraph_supervisor.models import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EducationExpertCard,
    EmotionalExpertCard,
    FirstModuleState,
    IntakeCard,
)
from app.llm.pool import pool

_MAX_ATTEMPTS = 3
_ANALYSIS_TEMPERATURE = 0.1
_EXPERT_TEMPERATURE = 0.2
_UNKNOWN_REASON_CONTEXT = "причина пользователю не известна"
_CAUSE_PROBE_MARKERS = (
    "почему",
    "из-за",
    "из за",
    "причин",
    "источник",
    "что случилось",
    "что именно вас беспокоит",
    "что именно беспокоит",
    "от чего",
)


def _context_has_unknown_reason(context: str | None) -> bool:
    return _UNKNOWN_REASON_CONTEXT in str(context or "").lower()


def _contains_cause_probe(text: str | None) -> bool:
    lowered = str(text or "").lower()
    return any(marker in lowered for marker in _CAUSE_PROBE_MARKERS)


def _normalize_unknown_reason_delegation_card(card: DelegationCard) -> DelegationCard:
    return DelegationCard(
        expert=DelegationExpert.EMOTIONAL_SUPPORT,
        task=(
            "оказать эмоциональную поддержку при грусти с неизвестной пользователю причиной; "
            "если понадобится уточнение, спрашивать только про длительность, интенсивность "
            "или влияние состояния на день, а не про источник причины"
        ),
        rationale=(
            "причина пользователю не известна, поэтому сначала нужна поддержка и "
            "безопасное уточнение текущего переживания"
        ),
    )


def _strip_code_fence(text: str) -> str:
    cleaned = str(text or "").strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()
    return cleaned


def _parse_field_block(text: str, required_fields: set[str]) -> dict[str, str]:
    cleaned = _strip_code_fence(text)
    if not cleaned:
        raise ValueError("empty field block")

    fields: dict[str, str] = {}
    for line_number, raw_line in enumerate(cleaned.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        if ":" not in line:
            raise ValueError(f"line {line_number} is not a field entry")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            raise ValueError(f"line {line_number} has empty field name")
        if key in fields:
            raise ValueError(f"duplicate field: {key}")
        fields[key] = value

    missing = sorted(required_fields.difference(fields))
    if missing:
        raise ValueError(f"missing required fields: {', '.join(missing)}")
    return fields


def _excerpt(text: str, limit: int = 200) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3] + "..."


def _append_failure(
    failures: list[dict[str, Any]],
    *,
    attempt: int,
    error: Exception,
    raw_text: str,
) -> None:
    failures.append(
        {
            "attempt": attempt,
            "error_type": error.__class__.__name__,
            "error_message": str(error),
            "raw_excerpt": _excerpt(raw_text),
        }
    )


def _build_step_diagnostics(
    *,
    attempts_total: int,
    succeeded_on_attempt: int | None,
    failures: list[dict[str, Any]],
    account_id: str,
    actual_model_tier: str,
    tokens_input: int,
    tokens_output: int,
    latency_ms: int,
) -> dict[str, Any]:
    return {
        "attempts_total": attempts_total,
        "succeeded_on_attempt": succeeded_on_attempt,
        "final_status": "success" if succeeded_on_attempt else "failed_after_retries",
        "failures": failures,
        "account_id": account_id,
        "actual_model_tier": actual_model_tier,
        "tokens_input": tokens_input,
        "tokens_output": tokens_output,
        "latency_ms": latency_ms,
    }


def _pending_question_text(state: FirstModuleState) -> str:
    pending = state.current_state.pending_question
    if pending is None:
        return "нет"
    return pending.question_text or "нет"


def _current_goal_text(state: FirstModuleState) -> str:
    if state.current_state.goal:
        return str(state.current_state.goal)
    return "нет"


def _active_intake_context_text(state: FirstModuleState) -> str:
    text = str(state.current_state.slots.get("intake_context") or "").strip()
    return text or "нет"


def _build_intake_retry_instruction(previous_error: str | None) -> str:
    if not previous_error:
        return ""
    return (
        "\nИсправь предыдущую ошибку и верни полную intake-карточку заново.\n"
        f"Предыдущая ошибка: {previous_error}\n"
        "Верни ровно 6 строк в этом порядке и не пропускай ни одной строки.\n"
        "Обязательные поля всегда: Проблема, Контекст, Нужно уточнение, Вопрос, Готово к передаче, Обоснование.\n"
        "Если Нужно уточнение: да, то Вопрос обязателен и не может быть 'нет'.\n"
        "Если Готово к передаче: да, то Нужно уточнение должно быть 'нет', а Вопрос должен быть 'нет'.\n"
        "Если Проблема = 'не обозначена', то Готово к передаче обязано быть 'нет', Нужно уточнение обязано быть 'да', и Вопрос обязан быть открывающим.\n"
        "Шаблон ответа:\n"
        "Проблема: ...\n"
        "Контекст: ...\n"
        "Нужно уточнение: ...\n"
        "Вопрос: ...\n"
        "Готово к передаче: ...\n"
        "Обоснование: ...\n"
    )


def build_intake_system_prompt(previous_error: str | None = None) -> str:
    return (
        "Роль: Ты intake-узел русскоязычного бота поддержки пациента.\n"
        "Твоя задача:\n"
        "- выделить главную проблему текущего сообщения;\n"
        "- кратко собрать контекст ситуации для передачи узлу-эксперту;\n"
        "- решить, нужен ли еще один уточняющий вопрос.\n"
        "Контекст пиши как 2-3 короткие фразы, только факты и обстоятельства, полезные для передачи дальше.\n"
        "Если в сообщении несколько проблем, выбери главную как Проблему, а остальные включи в Контекст.\n"
        "Если в диалоге уже есть накопленный контекст или открыт уточняющий вопрос, сохраняй этот якорь. "
        "Если новая реплика уточняет ту же тему, расширяй накопленный контекст, а не обнуляй его и не подменяй основную проблему узкой деталью.\n"
        "Если контекста еще недостаточно для передачи дальше, задай один лучший вопрос, который сильнее всего улучшит понимание ситуации.\n"
        "Если контекста уже достаточно, поставь:\n"
        "Готово к передаче: да\n"
        # Fix 3: снижаем порог ready_to_delegate — достаточно одного из условий
        "Контекста достаточно, если понятно хотя бы одно из перечисленного:\n"
        "- какая эмоция, ощущение или симптом беспокоит пациента;\n"
        "- есть хотя бы один конкретный триггер, обстоятельство или ситуация.\n"
        "Эксперт всегда может уточнить детали сам. Не держи пациента в фазе сбора контекста дольше необходимого.\n"
        "Ты не даешь coping, не даешь советы по существу, не выбираешь эксперта и не оказываешь поддержку.\n"
        "Верни только карточку, одно поле в строке, без JSON и без пояснений.\n"
        "Обязательно заполни ВСЕ 6 строк. Не пропускай последние строки даже если значение равно 'нет'.\n"
        "Строго соблюдай этот порядок строк:\n"
        "Проблема: ...\n"
        "Контекст: ...\n"
        "Нужно уточнение: ...\n"
        "Вопрос: ...\n"
        "Готово к передаче: ...\n"
        "Обоснование: ...\n"
        "Поля:\n"
        "Проблема: <кратко или 'не обозначена'>\n"
        "Контекст: <собери 2-3 коротких утверждения (только факты и обстоятельства), полезные для передачи дальше эксперту, или 'контекст пока не раскрыт'>\n"
        "Нужно уточнение: <да|нет>\n"
        "Вопрос: <один вопрос или 'нет'>\n"
        "Готово к передаче: <да|нет>\n"
        "Обоснование: <одна короткая строка>\n"
        "Правила:\n"
        # Fix 1: жёсткий лимит streak — при streak >= 2 с обозначенной проблемой всегда делегируй
        "- ОБЯЗАТЕЛЬНОЕ ПРАВИЛО: если clarification_streak >= 2 и Проблема уже обозначена "
        "(не равна 'не обозначена'), ты ОБЯЗАН поставить Готово к передаче: да, "
        "Нужно уточнение: нет, Вопрос: нет. Эксперт справится с тем контекстом, который уже собран.\n"
        "- Для приветствия без проблемы: Проблема = 'не обозначена', Готово к передаче = 'нет', Нужно уточнение = 'да', и задай один открывающий вопрос.\n"
        # Fix 2: правило дистресс-сообщений — условное, зависит от наличия конкретики в контексте
        "- Для общих дистресс-сообщений вроде 'мне тревожно', 'мне грустно', 'мне страшно', 'мне тяжело': "
        "задай один уточняющий вопрос, ЕСЛИ в текущем сообщении и накопленном контексте нет конкретного "
        "триггера, ситуации или причины. "
        "Не считай конкретикой: приветствие, общие утверждения ('мне плохо', 'мне тревожно') без деталей. "
        "Считай конкретикой: конкретную причину, событие, обстоятельство или симптом (например, 'боюсь диализа', "
        "'после операции', 'давление скачет', 'не сплю три дня'). "
        "Если конкретный триггер или ситуация уже присутствуют — переходи к делегации. "
        "Не задавай один и тот же уточняющий вопрос дважды.\n"
        "- Если есть открытый pending_question и пользователь отвечает в духе 'не знаю', 'не понимаю', "
        "'не могу объяснить', 'сам не знаю', 'просто ничего не радует' или иной близкой формулировкой, "
        "считай, что причина пользователю не известна. Не задавай новых уточнений: поставь "
        "Нужно уточнение: нет, Вопрос: нет, Готово к передаче: да, а в Контекст явно запиши "
        "'причина пользователю не известна' или равнозначную формулировку.\n"
        "- Если Проблема = 'не обозначена', Готово к передаче не может быть 'да'.\n"
        "- Не добавляй намерение, фазу, статус, экспертов и любые другие поля.\n"
        + _build_intake_retry_instruction(previous_error)
    )


def build_intake_user_prompt(state: FirstModuleState) -> str:
    return (
        "Последнее сообщение пользователя:\n"
        f"{state.user_message}\n\n"
        "Текущее состояние до этого хода:\n"
        f"- message_type: {state.message_type}\n"
        f"- current_goal: {_current_goal_text(state)}\n"
        f"- active_intake_context: {_active_intake_context_text(state)}\n"
        f"- pending_question: {_pending_question_text(state)}\n"
        f"- clarification_streak: {state.current_state.clarification_streak}\n"
        f"- signals: {', '.join(state.current_state.signals) or 'нет'}\n"
        f"- facts: {', '.join(state.current_state.facts) or 'нет'}\n"
        "Собери intake-карточку."
    )


def parse_intake_card(fields: dict[str, str]) -> IntakeCard:
    card = IntakeCard(
        problem=str(fields.get("Проблема") or "").strip(),
        context=str(fields.get("Контекст") or "").strip(),
        needs_clarification=BinaryChoice.parse(
            str(fields.get("Нужно уточнение") or "").strip(),
            field_name="Нужно уточнение",
        ),
        question=str(fields.get("Вопрос") or "").strip(),
        ready_to_delegate=BinaryChoice.parse(
            str(fields.get("Готово к передаче") or "").strip(),
            field_name="Готово к передаче",
        ),
        rationale=str(fields.get("Обоснование") or "").strip(),
    )
    validate_intake_card(card)
    return card


def validate_intake_card(card: IntakeCard) -> None:
    if not card.problem or not card.context or not card.rationale:
        raise ValueError("intake card has empty required text fields")
    if card.needs_clarification is BinaryChoice.YES and card.question in {"", "нет"}:
        raise ValueError("clarification requires a question")
    if card.ready_to_delegate is BinaryChoice.YES and card.needs_clarification is BinaryChoice.YES:
        raise ValueError("ready_to_delegate cannot coexist with clarification")
    if card.ready_to_delegate is BinaryChoice.YES and card.question not in {"", "нет"}:
        raise ValueError("ready_to_delegate requires question=нет")
    if card.problem == "не обозначена" and card.ready_to_delegate is BinaryChoice.YES:
        raise ValueError("undefined problem cannot be delegated")


def _build_delegation_retry_instruction(previous_error: str | None) -> str:
    if not previous_error:
        return ""
    return (
        "\nИсправь предыдущую ошибку и верни полную карточку делегации заново.\n"
        f"Предыдущая ошибка: {previous_error}\n"
        "Обязательные поля всегда: Эксперт, Задача, Обоснование.\n"
        "В этой версии допустимы только эксперты эмоциональная_поддержка и education.\n"
    )


def build_delegation_system_prompt(previous_error: str | None = None) -> str:
    return (
        "Ты delegation-узел русскоязычного бота поддержки пациента.\n"
        "Тебе уже переданы проблема и контекст. "
        "Твоя задача: выбрать одного эксперта и кратко сформулировать задачу для него.\n"
        "Не задавай вопрос пользователю и не давай помощь по существу.\n"
        "Верни только карточку, одно поле в строке:\n"
        "Эксперт: <эмоциональная_поддержка|education>\n"
        "Задача: <что должен сделать эксперт>\n"
        "Обоснование: <одна короткая строка>\n"
        "Выбирай education, только если есть локальный educational grounding и запрос требует короткого объяснения по теме.\n"
        "education подходит для явных запросов понять/объяснить/что это/почему так/нормально ли, "
        "а также для тревоги, которая держится из-за нехватки понимания процесса или состояния.\n"
        "Если локального educational grounding нет, не выбирай education.\n"
        "education не должен оказывать эмоциональную поддержку, диагностировать или выходить за пределы найденного контента.\n"
        "Если нужна в первую очередь поддержка состояния, выбирай эмоциональная_поддержка.\n"
        "Если в контексте явно сказано 'причина пользователю не известна', не ставь задачу "
        "выяснить причину или источник. В такой ситуации задача эксперта: поддержать пользователя "
        "и, если понадобится, мягко уточнить длительность, интенсивность или влияние состояния.\n"
        "ВАЖНО: значение поля Эксперт должно быть точно эмоциональная_поддержка или education.\n"
        + _build_delegation_retry_instruction(previous_error)
    )


def build_delegation_user_prompt(state: FirstModuleState) -> str:
    card = state.intake_card
    grounding_items = [dict(item) for item in (state.education_rag_grounding_items or []) if isinstance(item, dict)]
    prompt = (
        "Проблема пользователя:\n"
        f"{card.problem if card else 'нет'}\n\n"
        "Контекст:\n"
        f"{card.context if card else 'контекст пока не раскрыт'}\n\n"
        "Выбери эксперта и сформулируй задачу."
    )
    if grounding_items:
        prompt += "\n\nДоступный локальный educational grounding:"
        for item in grounding_items[:3]:
            lesson_title = str(item.get("lesson_title") or item.get("title") or "").strip() or "без названия"
            lesson_code = str(item.get("lesson_code") or "").strip()
            chunk = _excerpt(str(item.get("chunk") or ""), limit=180)
            prompt += f"\n- lesson_code={lesson_code or 'нет'} | {lesson_title}: {chunk}"
    else:
        prompt += "\n\nЛокальный educational grounding: нет."
    if _context_has_unknown_reason(card.context if card else None):
        prompt += (
            "\n\nСпециальное правило: причина пользователю не известна. "
            "Не формулируй задачу как поиск причины. Эксперт должен работать "
            "с текущим переживанием и, если нужно, уточнять только длительность, "
            "интенсивность или влияние состояния."
        )
    return prompt


def parse_delegation_card(fields: dict[str, str]) -> DelegationCard:
    card = DelegationCard(
        expert=DelegationExpert.parse(str(fields.get("Эксперт") or "").strip()),
        task=str(fields.get("Задача") or "").strip(),
        rationale=str(fields.get("Обоснование") or "").strip(),
    )
    validate_delegation_card(card)
    return card


def validate_delegation_card(card: DelegationCard) -> None:
    if card.expert not in {DelegationExpert.EMOTIONAL_SUPPORT, DelegationExpert.EDUCATION}:
        raise ValueError("delegation card contains unsupported expert")
    if not card.task or not card.rationale:
        raise ValueError("delegation card has empty required text fields")


def _build_expert_retry_instruction(previous_error: str | None) -> str:
    if not previous_error:
        return ""
    return (
        "\nИсправь предыдущую ошибку и верни полную карточку эксперта заново.\n"
        f"Предыдущая ошибка: {previous_error}\n"
        # Fix 6a retry: явные напоминания о двух паттернах ошибок
        "Карточка содержит ровно 4 поля в строгом порядке: Поддержка, Шаг сейчас, Вопрос пациенту, Обоснование.\n"
        "ПЕРВАЯ строка ОБЯЗАНА начинаться с 'Поддержка:' — не начинай с текста без метки поля.\n"
        "Поле 'Вопрос пациенту' ОБЯЗАТЕЛЬНО — пиши его всегда. Если вопроса нет: Вопрос пациенту: нет\n"
        "Не пропускай ни одно из 4 полей, даже если значение равно 'нет'.\n"
    )


def build_emotional_expert_system_prompt(previous_error: str | None = None) -> str:
    return (
        "Ты эксперт эмоциональной поддержки в русскоязычном боте пациента.\n"
        "Сначала коротко поддержи, потом предложи один конкретный безопасный шаг прямо сейчас, "
        "и только после этого, при необходимости, задай один мягкий вопрос.\n"
        "Шаг сейчас должен быть именно действием или предложением действия, а не вопросом.\n"
        "Не повторяй слова пользователя эхом. Не делай вид, что точно знаешь его внутреннее состояние. "
        "Не используй шаблонный coping без необходимости.\n"
        "Если в контексте явно сказано 'причина пользователю не известна', не пытайся выяснить причину, "
        "источник или ответ на вопрос 'почему'. Не спрашивай 'что случилось', 'почему', "
        "'что именно беспокоит' и похожие вопросы о причине. В этой ситуации допустимы только "
        "поддержка, безопасный шаг и, если правда нужно, один мягкий вопрос про длительность, "
        "интенсивность, телесные ощущения или влияние состояния на день.\n"
        # Fix 5: одно поле вместо двух конфликтующих (Уточнение после помощи + Нужно ли уточнение)
        # Fix 6a: явные правила формата, чтобы модель не пропускала поля и не писала текст без метки
        "Верни только карточку ровно из 4 строк, одно поле в строке, без JSON и без пояснений.\n"
        "Каждая строка ОБЯЗАНА начинаться с имени поля и двоеточия. "
        "Не начинай ни одну строку с текста без метки поля.\n"
        "Поддержка: <одна короткая живая фраза>\n"
        "Шаг сейчас: <один конкретный шаг>\n"
        "Вопрос пациенту: <один уточняющий вопрос или слово нет>\n"
        "Обоснование: <одна короткая строка>\n"
        "ВАЖНО: поле 'Вопрос пациенту' обязательно всегда — если вопроса нет, пиши: Вопрос пациенту: нет\n"
        + _build_expert_retry_instruction(previous_error)
    )


def build_emotional_expert_user_prompt(state: FirstModuleState) -> str:
    intake = state.intake_card
    delegation = state.delegation_card
    prompt = (
        "Проблема пользователя:\n"
        f"{intake.problem if intake else 'нет'}\n\n"
        "Контекст:\n"
        f"{intake.context if intake else 'контекст пока не раскрыт'}\n\n"
        "Задача эксперта:\n"
        f"{delegation.task if delegation else 'нет'}\n"
    )
    if _context_has_unknown_reason(intake.context if intake else None):
        prompt += (
            "\nОсобое ограничение: причина пользователю не известна. "
            "Не задавай вопрос о причине и не превращай 'Шаг сейчас' в вопрос. "
            "Если вопрос действительно нужен, он может быть только про длительность, "
            "интенсивность, телесные ощущения или влияние состояния на день."
        )
    return prompt


def parse_emotional_expert_card(fields: dict[str, str]) -> EmotionalExpertCard:
    # Fix 5: единое поле "Вопрос пациенту" — вопрос или 'нет'.
    # needs_more_info выводится автоматически: есть вопрос → да, иначе → нет.
    # Fix 6b: регистронезависимое сравнение — модель может написать "Нет", "НЕТ" и т.д.
    follow_up = str(fields.get("Вопрос пациенту") or "").strip()
    needs_more = follow_up.lower() not in {"", "нет"}
    card = EmotionalExpertCard(
        support=str(fields.get("Поддержка") or "").strip(),
        step_now=str(fields.get("Шаг сейчас") or "").strip(),
        follow_up=follow_up,
        needs_more_info=BinaryChoice.YES if needs_more else BinaryChoice.NO,
        rationale=str(fields.get("Обоснование") or "").strip(),
    )
    validate_emotional_expert_card(card)
    return card


def validate_emotional_expert_card(card: EmotionalExpertCard) -> None:
    if not card.support or not card.step_now or not card.rationale:
        raise ValueError("expert card has empty required text fields")
    if "?" in card.step_now:
        raise ValueError("step_now must be an action, not a question")
    # needs_more_info выводится из follow_up, поэтому конфликт поля невозможен


def _lookup_grounded_lesson_target(
    state: FirstModuleState,
    lesson_code: str | None,
) -> tuple[str | None, dict[str, Any] | None]:
    normalized_code = str(lesson_code or "").strip()
    if not normalized_code or normalized_code.lower() == "нет":
        return None, None

    for item in state.education_rag_grounding_items or []:
        if not isinstance(item, dict):
            continue
        item_code = str(item.get("lesson_code") or "").strip()
        if item_code != normalized_code:
            continue
        label = str(item.get("lesson_title") or item.get("title") or "").strip() or None
        target = {
            "lesson_id": int(item.get("lesson_id")),
            "lesson_code": item_code,
        }
        return label, target
    raise ValueError("education CTA references lesson outside current grounding")


def _build_education_retry_instruction(previous_error: str | None) -> str:
    if not previous_error:
        return ""
    return (
        "\nИсправь предыдущую ошибку и верни полную карточку education-эксперта заново.\n"
        f"Предыдущая ошибка: {previous_error}\n"
        "Карточка содержит ровно 5 полей в строгом порядке: Объяснение, CTA тип, CTA заголовок, CTA lesson_code, Обоснование.\n"
        "CTA тип может быть только lesson или none.\n"
        "Если CTA тип = none, пиши CTA заголовок: нет и CTA lesson_code: нет.\n"
        "Если CTA тип = lesson, lesson_code должен совпадать с одним из доступных локальных материалов.\n"
    )


def build_education_expert_system_prompt(previous_error: str | None = None) -> str:
    return (
        "Ты education-эксперт в русскоязычном боте поддержки пациента.\n"
        "Твоя задача: коротко и простыми словами объяснить текущую тему, строго опираясь только на переданные локальные educational материалы.\n"
        "Не диагностируй, не обещай медицинскую интерпретацию, не выходи за пределы найденных фрагментов.\n"
        "Если подходящий урок есть, мягко предложи его как следующий шаг. В этой версии основной CTA только на lesson.\n"
        "Верни только карточку ровно из 5 строк, одно поле в строке, без JSON и без пояснений.\n"
        "Объяснение: <1-2 короткие фразы>\n"
        "CTA тип: <lesson|none>\n"
        "CTA заголовок: <название урока или нет>\n"
        "CTA lesson_code: <lesson_code или нет>\n"
        "Обоснование: <одна короткая строка>\n"
        "Если уверенного lesson CTA нет, используй CTA тип: none.\n"
        + _build_education_retry_instruction(previous_error)
    )


def build_education_expert_user_prompt(state: FirstModuleState) -> str:
    intake = state.intake_card
    delegation = state.delegation_card
    prompt = (
        "Проблема пользователя:\n"
        f"{intake.problem if intake else 'нет'}\n\n"
        "Контекст:\n"
        f"{intake.context if intake else 'контекст пока не раскрыт'}\n\n"
        "Задача эксперта:\n"
        f"{delegation.task if delegation else 'нет'}\n\n"
        "Доступные локальные материалы:\n"
    )
    grounding_items = [dict(item) for item in (state.education_rag_grounding_items or []) if isinstance(item, dict)]
    if not grounding_items:
        prompt += "нет\n"
        return prompt

    for item in grounding_items[:3]:
        lesson_code = str(item.get("lesson_code") or "").strip() or "нет"
        lesson_title = str(item.get("lesson_title") or item.get("title") or "").strip() or "без названия"
        chunk = _excerpt(str(item.get("chunk") or ""), limit=220)
        prompt += f"- lesson_code={lesson_code}; title={lesson_title}; fragment={chunk}\n"
    return prompt.rstrip()


def parse_education_expert_card(fields: dict[str, str], state: FirstModuleState) -> EducationExpertCard:
    explanation = str(fields.get("Объяснение") or "").strip()
    cta_type = str(fields.get("CTA тип") or "").strip().lower()
    cta_label_raw = str(fields.get("CTA заголовок") or "").strip()
    cta_lesson_code_raw = str(fields.get("CTA lesson_code") or "").strip()

    if cta_type not in {"lesson", "none"}:
        raise ValueError("education CTA type must be lesson or none")

    cta_label: str | None = None
    cta_target: dict[str, Any] | None = None
    if cta_type == "lesson":
        cta_label, cta_target = _lookup_grounded_lesson_target(state, cta_lesson_code_raw)
        if cta_label is None:
            cta_label = cta_label_raw if cta_label_raw.lower() != "нет" else None
    else:
        if cta_label_raw.lower() not in {"", "нет"} or cta_lesson_code_raw.lower() not in {"", "нет"}:
            raise ValueError("education CTA none must not include lesson reference")

    card = EducationExpertCard(
        explanation=explanation,
        cta_type=cta_type,
        cta_label=cta_label,
        cta_target=cta_target,
        rationale=str(fields.get("Обоснование") or "").strip(),
    )
    validate_education_expert_card(card)
    return card


def validate_education_expert_card(card: EducationExpertCard) -> None:
    if not card.explanation or not card.rationale:
        raise ValueError("education expert card has empty required text fields")
    if card.cta_type not in {"lesson", "none"}:
        raise ValueError("education expert card has unsupported CTA type")
    if card.cta_type == "lesson":
        if not card.cta_label or not isinstance(card.cta_target, dict):
            raise ValueError("education lesson CTA requires label and target")
        if "lesson_id" not in card.cta_target or "lesson_code" not in card.cta_target:
            raise ValueError("education lesson CTA target is incomplete")
    elif card.cta_label is not None or card.cta_target is not None:
        raise ValueError("education none CTA must not include target")


async def _call_structured_llm(
    *,
    system_prompt: str,
    user_prompt: str,
    model_tier: str,
    strict_model_tier: bool,
    temperature: float,
) -> tuple[str, str, int, int, int]:
    try:
        client = await pool.get_available(strict=strict_model_tier)
    except RuntimeError as exc:
        raise LLMConfigurationError(str(exc)) from exc

    text, tokens_in, tokens_out, latency_ms = await client.call(
        [{"role": "user", "content": user_prompt}],
        system_prompt,
        model_tier=model_tier,
        temperature=temperature,
    )
    return str(text or ""), client.account_id, int(tokens_in or 0), int(tokens_out or 0), int(latency_ms or 0)


async def extract_intake_card(state: FirstModuleState) -> tuple[IntakeCard | None, dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    previous_error: str | None = None
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0
    last_account_id = ""

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw_text, account_id, tokens_in, tokens_out, latency_ms = await _call_structured_llm(
            system_prompt=build_intake_system_prompt(previous_error),
            user_prompt=build_intake_user_prompt(state),
            model_tier=state.model_tier,
            strict_model_tier=state.strict_model_tier,
            temperature=_ANALYSIS_TEMPERATURE,
        )
        last_account_id = account_id
        total_tokens_in += tokens_in
        total_tokens_out += tokens_out
        total_latency_ms += latency_ms
        state.register_llm_call(
            account_id=account_id,
            actual_model_tier=state.model_tier,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        try:
            fields = _parse_field_block(
                raw_text,
                {"Проблема", "Контекст", "Нужно уточнение", "Вопрос", "Готово к передаче", "Обоснование"},
            )
            return parse_intake_card(fields), _build_step_diagnostics(
                attempts_total=attempt,
                succeeded_on_attempt=attempt,
                failures=failures,
                account_id=last_account_id,
                actual_model_tier=state.model_tier,
                tokens_input=total_tokens_in,
                tokens_output=total_tokens_out,
                latency_ms=total_latency_ms,
            )
        except (TypeError, ValueError) as exc:
            previous_error = str(exc)
            _append_failure(failures, attempt=attempt, error=exc, raw_text=raw_text)

    return None, _build_step_diagnostics(
        attempts_total=_MAX_ATTEMPTS,
        succeeded_on_attempt=None,
        failures=failures,
        account_id=last_account_id,
        actual_model_tier=state.model_tier,
        tokens_input=total_tokens_in,
        tokens_output=total_tokens_out,
        latency_ms=total_latency_ms,
    )


async def extract_delegation_card(state: FirstModuleState) -> tuple[DelegationCard | None, dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    previous_error: str | None = None
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0
    last_account_id = ""

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw_text, account_id, tokens_in, tokens_out, latency_ms = await _call_structured_llm(
            system_prompt=build_delegation_system_prompt(previous_error),
            user_prompt=build_delegation_user_prompt(state),
            model_tier=state.model_tier,
            strict_model_tier=state.strict_model_tier,
            temperature=_ANALYSIS_TEMPERATURE,
        )
        last_account_id = account_id
        total_tokens_in += tokens_in
        total_tokens_out += tokens_out
        total_latency_ms += latency_ms
        state.register_llm_call(
            account_id=account_id,
            actual_model_tier=state.model_tier,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        try:
            fields = _parse_field_block(raw_text, {"Эксперт", "Задача", "Обоснование"})
            card = parse_delegation_card(fields)
            if _context_has_unknown_reason(getattr(state.intake_card, "context", None)):
                card = _normalize_unknown_reason_delegation_card(card)
            if card.expert is DelegationExpert.EDUCATION and not state.education_rag_grounding_items:
                raise ValueError("education expert requires local educational grounding")
            return card, _build_step_diagnostics(
                attempts_total=attempt,
                succeeded_on_attempt=attempt,
                failures=failures,
                account_id=last_account_id,
                actual_model_tier=state.model_tier,
                tokens_input=total_tokens_in,
                tokens_output=total_tokens_out,
                latency_ms=total_latency_ms,
            )
        except (TypeError, ValueError) as exc:
            previous_error = str(exc)
            _append_failure(failures, attempt=attempt, error=exc, raw_text=raw_text)

    return None, _build_step_diagnostics(
        attempts_total=_MAX_ATTEMPTS,
        succeeded_on_attempt=None,
        failures=failures,
        account_id=last_account_id,
        actual_model_tier=state.model_tier,
        tokens_input=total_tokens_in,
        tokens_output=total_tokens_out,
        latency_ms=total_latency_ms,
    )


async def extract_emotional_expert_card(state: FirstModuleState) -> tuple[EmotionalExpertCard | None, dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    previous_error: str | None = None
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0
    last_account_id = ""

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw_text, account_id, tokens_in, tokens_out, latency_ms = await _call_structured_llm(
            system_prompt=build_emotional_expert_system_prompt(previous_error),
            user_prompt=build_emotional_expert_user_prompt(state),
            model_tier=state.model_tier,
            strict_model_tier=state.strict_model_tier,
            temperature=_EXPERT_TEMPERATURE,
        )
        last_account_id = account_id
        total_tokens_in += tokens_in
        total_tokens_out += tokens_out
        total_latency_ms += latency_ms
        state.register_llm_call(
            account_id=account_id,
            actual_model_tier=state.model_tier,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        try:
            fields = _parse_field_block(
                raw_text,
                {"Поддержка", "Шаг сейчас", "Вопрос пациенту", "Обоснование"},
            )
            card = parse_emotional_expert_card(fields)
            if _context_has_unknown_reason(getattr(state.intake_card, "context", None)):
                if _contains_cause_probe(card.step_now) or _contains_cause_probe(card.follow_up):
                    raise ValueError("unknown-reason flow must not ask about cause/source")
            return card, _build_step_diagnostics(
                attempts_total=attempt,
                succeeded_on_attempt=attempt,
                failures=failures,
                account_id=last_account_id,
                actual_model_tier=state.model_tier,
                tokens_input=total_tokens_in,
                tokens_output=total_tokens_out,
                latency_ms=total_latency_ms,
            )
        except (TypeError, ValueError) as exc:
            previous_error = str(exc)
            _append_failure(failures, attempt=attempt, error=exc, raw_text=raw_text)

    return None, _build_step_diagnostics(
        attempts_total=_MAX_ATTEMPTS,
        succeeded_on_attempt=None,
        failures=failures,
        account_id=last_account_id,
        actual_model_tier=state.model_tier,
        tokens_input=total_tokens_in,
        tokens_output=total_tokens_out,
        latency_ms=total_latency_ms,
    )


async def extract_education_expert_card(state: FirstModuleState) -> tuple[EducationExpertCard | None, dict[str, Any]]:
    if not state.education_rag_grounding_items:
        return None, {
            "attempts_total": 0,
            "succeeded_on_attempt": None,
            "final_status": "failed_after_retries",
            "failures": [{"attempt": 0, "error_type": "ValueError", "error_message": "missing education grounding"}],
        }

    failures: list[dict[str, Any]] = []
    previous_error: str | None = None
    total_tokens_in = 0
    total_tokens_out = 0
    total_latency_ms = 0
    last_account_id = ""

    for attempt in range(1, _MAX_ATTEMPTS + 1):
        raw_text, account_id, tokens_in, tokens_out, latency_ms = await _call_structured_llm(
            system_prompt=build_education_expert_system_prompt(previous_error),
            user_prompt=build_education_expert_user_prompt(state),
            model_tier=state.model_tier,
            strict_model_tier=state.strict_model_tier,
            temperature=_EXPERT_TEMPERATURE,
        )
        last_account_id = account_id
        total_tokens_in += tokens_in
        total_tokens_out += tokens_out
        total_latency_ms += latency_ms
        state.register_llm_call(
            account_id=account_id,
            actual_model_tier=state.model_tier,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
        )
        try:
            fields = _parse_field_block(
                raw_text,
                {"Объяснение", "CTA тип", "CTA заголовок", "CTA lesson_code", "Обоснование"},
            )
            card = parse_education_expert_card(fields, state)
            return card, _build_step_diagnostics(
                attempts_total=attempt,
                succeeded_on_attempt=attempt,
                failures=failures,
                account_id=last_account_id,
                actual_model_tier=state.model_tier,
                tokens_input=total_tokens_in,
                tokens_output=total_tokens_out,
                latency_ms=total_latency_ms,
            )
        except (TypeError, ValueError) as exc:
            previous_error = str(exc)
            _append_failure(failures, attempt=attempt, error=exc, raw_text=raw_text)

    return None, _build_step_diagnostics(
        attempts_total=_MAX_ATTEMPTS,
        succeeded_on_attempt=None,
        failures=failures,
        account_id=last_account_id,
        actual_model_tier=state.model_tier,
        tokens_input=total_tokens_in,
        tokens_output=total_tokens_out,
        latency_ms=total_latency_ms,
    )


def build_intake_reply(card: IntakeCard) -> str:
    if card.question in {"", "нет"}:
        return ""
    if card.problem == "не обозначена":
        return f"Привет. {card.question}"
    return f"Сочувствую. {card.question}"


def build_emotional_reply(card: EmotionalExpertCard) -> str:
    parts = [card.support, card.step_now]
    # Fix 6c: регистронезависимое сравнение — не выводить "Нет" / "НЕТ" как часть ответа
    if card.needs_more_info is BinaryChoice.YES and card.follow_up.lower() not in {"", "нет"}:
        parts.append(card.follow_up)
    return " ".join(part.strip() for part in parts if str(part or "").strip()).strip()


def build_education_reply(card: EducationExpertCard) -> str:
    parts = [card.explanation]
    if card.cta_type == "lesson" and card.cta_label:
        parts.append(f"Если хочешь, можно посмотреть урок «{card.cta_label}».")
    return " ".join(part.strip() for part in parts if str(part or "").strip()).strip()


def build_finish_reply(user_message: str) -> str:
    lowered = str(user_message or "").strip().lower()
    if lowered in {"спасибо", "спс", "благодарю"}:
        return "Пожалуйста."
    if lowered in {"понятно", "угу", "ок", "хорошо"}:
        return "Хорошо."
    return "Я рядом."
