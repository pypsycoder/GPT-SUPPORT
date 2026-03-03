"""
LLM Agent — сборка промптов и вызов GigaChat API.

Функция generate_response:
  1. Выбирает системный промпт (base_system + domain_*)
  2. Собирает messages для API
  3. Получает клиента из пула
  4. Делает запрос
  5. Логирует в llm_request_logs
  6. Возвращает результат
"""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.llm.pool import pool
from app.llm.router import RouterResult, RequestType
from app.llm.keywords import MEDICATION_KEYWORDS

# Постфикс для кризисных ситуаций — добавляется на уровне кода, не промпта
CRISIS_POSTFIX = (
    "\n\nЕсли тебе сейчас очень плохо — позвони:\n"
    "📞 Телефон доверия: 8-800-2000-122 (бесплатно, круглосуточно)\n"
    "🚑 Скорая помощь: 103"
)

logger = logging.getLogger("gpt-support-llm.agent")

# ---------------------------------------------------------------------------
# Постобработка ответов
# ---------------------------------------------------------------------------

_SOFTENER_PHRASES = [
    "но ничего страшного",
    "ничего страшного",
    "не страшно",
]

def _strip_softeners(text: str) -> str:
    """Убирает обесценивающие фразы из ответа модели (только для критичных доменов)."""
    for phrase in _SOFTENER_PHRASES:
        text = re.sub(
            rf',?\s*(но\s+)?{re.escape(phrase)}[,.]?\s*',
            ' ',
            text,
            flags=re.IGNORECASE,
        )
    # Убираем задвоенные пробелы после замены
    text = re.sub(r' {2,}', ' ', text)
    return text.strip()

# ---------------------------------------------------------------------------
# Промпты
# ---------------------------------------------------------------------------

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_prompt_cache: dict[str, str] = {}


def load_prompt(filename: str) -> str:
    """
    Читает файл промпта из app/llm/prompts/, кэширует результат.

    Args:
        filename: имя файла (например "base_system.txt")

    Returns:
        Содержимое файла.

    Raises:
        FileNotFoundError: если файл не существует.
    """
    if filename in _prompt_cache:
        return _prompt_cache[filename]

    path = _PROMPTS_DIR / filename
    text = path.read_text(encoding="utf-8").strip()
    _prompt_cache[filename] = text
    return text


def _build_system_prompt(domain_hint: str | None) -> str:
    """Объединяет base_system.txt с domain-специфичным промптом (если есть)."""
    base = load_prompt("base_system.txt")

    if domain_hint:
        domain_file = f"domain_{domain_hint}.txt"
        try:
            domain_extra = load_prompt(domain_file)
            return f"{base}\n\n{domain_extra}"
        except FileNotFoundError:
            logger.debug("[agent] Нет domain-промпта: %s", domain_file)

    return base


# ---------------------------------------------------------------------------
# Основная функция
# ---------------------------------------------------------------------------

async def generate_response(
    patient_id: int,
    user_input: str,
    router_result: RouterResult,
    context: dict,
    db: AsyncSession,
) -> dict:
    """
    Генерирует ответ LLM и логирует запрос в БД.

    Args:
        patient_id:    ID пациента
        user_input:    текст запроса пользователя
        router_result: результат classify_request()
        context:       дополнительный контекст (history и пр., опционально)
        db:            AsyncSession для логирования

    Returns:
        {
          "response": str,
          "tokens_input": int,
          "tokens_output": int,
          "model": str,
          "domain": str | None,
          "response_time_ms": int,
          "account_id": str,
        }
    """
    from app.llm.context_builder import build_context, format_context_for_llm
    from app.models.llm import LLMRequestLog  # локальный импорт избегает циклов

    # 1. Собираем данные пациента из БД (включая RAG-контекст по тексту запроса)
    patient_context = await build_context(patient_id, db, query=user_input)
    context_text = format_context_for_llm(patient_context)

    # 1b. Парсим сообщение пациента для извлечения структурированных данных
    _parsed_domain_hints: list[str] = []
    _pending_vitals: list[dict] = []
    try:
        if len(user_input) > 7:
            from app.llm.parser import parse_patient_message
            parsed = await parse_patient_message(user_input, patient_id, db)
            logger.info("[agent] parsed: %s", parsed)
            if parsed:
                # Витальные НЕ записываем в БД — возвращаем для подтверждения пациентом
                raw_vitals = parsed.get("vitals", [])
                if raw_vitals:
                    from app.llm.parser import normalize_bp, normalize_pulse
                    for v in raw_vitals:
                        vtype = str(v.get("type", "")).upper()
                        value = v.get("value", "")
                        valid = False
                        try:
                            if vtype == "BP":
                                valid = normalize_bp(value) is not None
                            elif vtype == "PULSE":
                                valid = normalize_pulse(value) is not None
                            elif vtype == "WEIGHT":
                                float(str(value).strip())
                                valid = True
                            elif vtype == "WATER":
                                int(float(str(value).strip()))
                                valid = True
                        except (ValueError, AttributeError):
                            pass
                        if valid:
                            _pending_vitals.append({"type": vtype, "value": value})
                        else:
                            logger.warning("[agent] пропускаем невалидный витал %s=%r", vtype, value)
                # Добавляем настроение в контекст пациента
                mood = parsed.get("mood", "unknown")
                if mood and mood != "unknown":
                    mood_line = f"Настроение: {mood}"
                    context_text = f"{mood_line}\n{context_text}" if context_text else mood_line
                # Подсказки домена для выбора промпта
                _parsed_domain_hints = parsed.get("domain_hints", [])
    except Exception as exc:
        logger.warning("[agent] ошибка парсера, продолжаем без него: %s", exc)

    # 2. Строим системный промпт с контекстом пациента
    effective_domain = router_result.domain_hint or (_parsed_domain_hints[0] if _parsed_domain_hints else None)
    system_prompt = _build_system_prompt(effective_domain)
    if context_text:
        system_prompt = f"{system_prompt}\n\n{context_text}"
    # Дневной контекст (диализ, лекарства, пропуски) — если передан из chat endpoint
    daily_ctx = context.get("daily_context", "")
    if daily_ctx:
        system_prompt = f"{system_prompt}\n\n{daily_ctx}"

    # История: из patient_context (chat_history) или из переданного context
    history: list[dict] = patient_context.get("chat_history") or context.get("history", [])
    messages: list[dict] = [
        *history,
        {"role": "user", "content": user_input},
    ]

    # Получаем клиента из пула
    client = await pool.get_available(router_result.model_tier.value)

    success = False
    error_message: str | None = None
    response_text = ""
    tokens_in = 0
    tokens_out = 0
    elapsed_ms = 0

    start = time.monotonic()
    try:
        response_text, tokens_in, tokens_out, elapsed_ms = await client.call(
            messages, system_prompt
        )
        success = True
        # Добавляем номера телефонов для кризисных ситуаций
        if router_result.request_type == RequestType.SAFETY:
            response_text += CRISIS_POSTFIX
        # Убираем обесценивающие фразы при пропуске лекарств
        if router_result.domain_hint == "routine":
            lower_input = user_input.lower()
            if any(kw in lower_input for kw in MEDICATION_KEYWORDS):
                response_text = _strip_softeners(response_text)
        from app.llm.pool import MODEL_NAMES as _MODEL_NAMES
        logger.info(
            "[agent] patient=%s domain=%s model=%s\n  Q: %s\n  A: %s",
            patient_id,
            router_result.domain_hint,
            _MODEL_NAMES.get(router_result.model_tier.value, "unknown"),
            user_input[:100],
            response_text[:200],
        )
    except Exception as exc:
        error_message = str(exc)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error(
            "[agent] Ошибка LLM patient=%d account=%s: %s",
            patient_id, client.account_id, exc,
        )
        raise

    finally:
        # Логируем запрос в БД независимо от результата
        from app.llm.pool import MODEL_NAMES
        log = LLMRequestLog(
            patient_id=patient_id,
            account_id=client.account_id,
            model_tier=router_result.model_tier.value,
            tokens_input=tokens_in,
            tokens_output=tokens_out,
            response_time_ms=elapsed_ms,
            request_type=router_result.request_type.value,
            success=success,
            error_message=error_message,
        )
        db.add(log)
        await db.flush()

    from app.llm.pool import MODEL_NAMES
    return {
        "response": response_text,
        "tokens_input": tokens_in,
        "tokens_output": tokens_out,
        "model": MODEL_NAMES.get(router_result.model_tier.value, "unknown"),
        "domain": router_result.domain_hint,
        "response_time_ms": elapsed_ms,
        "account_id": client.account_id,
        "pending_vitals": _pending_vitals or None,
    }
