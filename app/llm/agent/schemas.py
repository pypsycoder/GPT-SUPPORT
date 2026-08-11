"""Контракт финального ответа одноагентной ветки (шаг 4).

Схема плоская: только строки, ``Literal``, целые и список строк. Вложенные
модели и Enum Pydantic вынес бы в ``$defs`` + ``$ref``, а это ломает
strict-режим GigaChat (см. ``app.llm.structured``).

Имена полей латинские и совпадают с тем, как модель называет их сама. Русские
алиасы здесь пробовались и провалились: GigaChat возвращал ``intent`` /
``response`` / ``risk_level`` вместо кириллических ключей, и валидация падала на
каждом вызове. В карточках супервизора кириллица работает только потому, что
системный промпт перечисляет ключи дословно — здесь мы делаем то же самое
(см. ``prompts.AGENT_SYSTEM_PROMPT``), но на именах, которые модель и так
выбирает по умолчанию.

Зачем схема, если пациенту нужен просто текст: вместе с текстом одним вызовом
приходят маршрутные поля — safety, следующий шаг, кандидаты в память. В старой
ветке на это уходили отдельные вызовы intake, delegation и эксперта.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SafetyLevel = Literal["none", "concern", "urgent"]
SafetyKind = Literal["psychological", "medical", "none"]
Intent = Literal["emotional_support", "education", "smalltalk", "safety"]

# Перечисление ключей для системного промпта: модель обязана знать их дословно.
AGENT_REPLY_KEYS = (
    "reply, intent, technique_id, safety_level, safety_kind, safety_reason, "
    "next_action, memory_candidates, rationale"
)


class AgentReply(BaseModel):
    """Один структурный ответ вместо цепочки intake → delegation → expert."""

    model_config = ConfigDict(extra="forbid")

    reply: str = Field(
        max_length=1200,
        description="Текст пациенту на русском, 2-5 предложений, без markdown",
    )
    intent: Intent = Field(description="Что пациенту нужно прямо сейчас")
    # Прогресс по технике считается по этому полю, а не по префиксу [pNN],
    # выковырянному из текста ответа: в старой ветке такой разбор застревал.
    technique_id: str = Field(
        max_length=16,
        description=(
            "id техники из блока подходящих техник, если ты передал её пациенту "
            "(например p01), иначе 'нет'"
        ),
    )
    safety_level: SafetyLevel = Field(
        description="none — обычный разговор; concern — тревожные признаки; urgent — угроза жизни"
    )
    # Вид нужен второму эшелону, чтобы подставить правильный протокол: телефон
    # доверия при передозировке — вредный совет, а разговор о скорой при
    # суицидальных мыслях не отвечает на то, что человек сказал.
    safety_kind: SafetyKind = Field(
        description=(
            "psychological — про смерть или самоповреждение; "
            "medical — острое состояние тела; none — риска нет"
        )
    )
    safety_reason: str = Field(
        max_length=200,
        description="Одна строка на русском, почему выбран уровень, или 'нет'",
    )
    next_action: str = Field(
        max_length=120,
        description="Что предложить дальше — урок, практика, запись показателей, или 'нет'",
    )
    # Без default: поле с дефолтом выпадает из required, а без required модель
    # возвращает произвольный JSON даже при strict:true. Пустой список — валидное
    # значение, его модель и должна прислать, когда запоминать нечего.
    memory_candidates: list[str] = Field(
        max_length=3,
        description="Устойчивые факты о пациенте, или пустой список. Решение о записи принимает не модель",
    )
    rationale: str = Field(
        max_length=200,
        description="Одна короткая строка для отладки, пациенту не показывается",
    )
