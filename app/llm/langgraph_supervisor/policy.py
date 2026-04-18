"""Prompting, parsing, and validation helpers for Graph v2."""

from __future__ import annotations

from typing import Any

from app.llm.errors import LLMConfigurationError
from app.llm.langgraph_supervisor.models import (
    BinaryChoice,
    DelegationCard,
    DelegationExpert,
    EmotionalExpertCard,
    FirstModuleState,
    IntakeCard,
)
from app.llm.pool import pool

_MAX_ATTEMPTS = 3
_ANALYSIS_TEMPERATURE = 0.1
_EXPERT_TEMPERATURE = 0.2


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
        "На этой версии допустим только эксперт эмоциональная_поддержка.\n"
    )


def build_delegation_system_prompt(previous_error: str | None = None) -> str:
    return (
        "Ты delegation-узел русскоязычного бота поддержки пациента.\n"
        "Тебе уже переданы проблема и контекст. "
        "Твоя задача: выбрать одного эксперта и кратко сформулировать задачу для него.\n"
        "Не задавай вопрос пользователю и не давай помощь по существу.\n"
        "Верни только карточку, одно поле в строке:\n"
        "Эксперт: <эмоциональная_поддержка>\n"
        "Задача: <что должен сделать эксперт>\n"
        "Обоснование: <одна короткая строка>\n"
        # Явное напоминание про подчёркивание — модель иначе пишет пробел
        "ВАЖНО: значение поля Эксперт должно быть точно эмоциональная_поддержка "
        "(нижнее подчёркивание, не пробел, не дефис).\n"
        + _build_delegation_retry_instruction(previous_error)
    )


def build_delegation_user_prompt(state: FirstModuleState) -> str:
    card = state.intake_card
    return (
        "Проблема пользователя:\n"
        f"{card.problem if card else 'нет'}\n\n"
        "Контекст:\n"
        f"{card.context if card else 'контекст пока не раскрыт'}\n\n"
        "Выбери эксперта и сформулируй задачу."
    )


def parse_delegation_card(fields: dict[str, str]) -> DelegationCard:
    card = DelegationCard(
        expert=DelegationExpert.parse(str(fields.get("Эксперт") or "").strip()),
        task=str(fields.get("Задача") or "").strip(),
        rationale=str(fields.get("Обоснование") or "").strip(),
    )
    validate_delegation_card(card)
    return card


def validate_delegation_card(card: DelegationCard) -> None:
    if card.expert is not DelegationExpert.EMOTIONAL_SUPPORT:
        raise ValueError("only эмоциональная_поддержка is supported in v1")
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
        "Не повторяй слова пользователя эхом. Не делай вид, что точно знаешь его внутреннее состояние. "
        "Не используй шаблонный coping без необходимости.\n"
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
    return (
        "Проблема пользователя:\n"
        f"{intake.problem if intake else 'нет'}\n\n"
        "Контекст:\n"
        f"{intake.context if intake else 'контекст пока не раскрыт'}\n\n"
        "Задача эксперта:\n"
        f"{delegation.task if delegation else 'нет'}\n"
    )


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
    # needs_more_info выводится из follow_up, поэтому конфликт поля невозможен


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
            return parse_delegation_card(fields), _build_step_diagnostics(
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
            return parse_emotional_expert_card(fields), _build_step_diagnostics(
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


def build_finish_reply(user_message: str) -> str:
    lowered = str(user_message or "").strip().lower()
    if lowered in {"спасибо", "спс", "благодарю"}:
        return "Пожалуйста."
    if lowered in {"понятно", "угу", "ок", "хорошо"}:
        return "Хорошо."
    return "Я рядом."
