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

from pydantic import BaseModel, ConfigDict, Field, field_validator

SafetyLevel = Literal["none", "concern", "urgent"]
SafetyKind = Literal["psychological", "medical", "none"]
Intent = Literal["emotional_support", "education", "smalltalk", "safety"]

# Перечисление ключей для системного промпта: модель обязана знать их дословно.
# Список короткий намеренно. На девяти ключах GigaChat начал их обрезать —
# присылал safekind и safetreason вместо полных имён, и карточка падала целиком
# (15 откатов из 16 на замере). Каждое новое поле здесь стоит не только токенов,
# но и устойчивости всех остальных.
AGENT_REPLY_KEYS = (
    "reply, intent, technique_id, safety_level, safety_kind, safety_reason, "
    "next_action, memory_candidates"
)


class AgentReply(BaseModel):
    """Один структурный ответ вместо цепочки intake → delegation → expert."""

    # extra="ignore", а не "forbid": на коротких репликах модель иногда обрезает
    # имя ключа (присылала safekind вместо safety_kind). Ронять из-за этого всю
    # карточку и уходить на откат — хуже, чем проигнорировать лишний ключ.
    model_config = ConfigDict(extra="ignore")

    # Обязательны только три поля, которые нечем заменить по умолчанию.
    # Раньше обязательными были все восемь — по документации GigaChat, где
    # сказано, что без required модель возвращает произвольный JSON. На замере
    # это дало обратный эффект: на «привет» и «спасибо» модель обрывала карточку
    # после первых полей, валидация падала целиком, и 4 из 5 коротких реплик
    # уходили на откат к старой ветке. Потеря необязательного поля дешевле
    # потери всей карточки, а smalltalk — 40% реального трафика.
    reply: str = Field(
        max_length=1200,
        description="Текст пациенту на русском, 2-5 предложений, без markdown",
    )
    intent: Intent = Field(description="Что пациенту нужно прямо сейчас")
    safety_level: SafetyLevel = Field(
        description="none — обычный разговор; concern — тревожные признаки; urgent — угроза жизни"
    )
    # Прогресс по технике считается по этому полю, а не по префиксу [pNN],
    # выковырянному из текста ответа: в старой ветке такой разбор застревал.
    technique_id: str = Field(
        default="нет",
        max_length=16,
        description=(
            "id техники из блока подходящих техник, если ты передал её пациенту "
            "(например p01), иначе 'нет'"
        ),
    )
    # Вид нужен второму эшелону, чтобы подставить правильный протокол: телефон
    # доверия при передозировке — вредный совет, а разговор о скорой при
    # суицидальных мыслях не отвечает на то, что человек сказал.
    safety_kind: SafetyKind = Field(
        default="none",
        description=(
            "psychological — про смерть или самоповреждение; "
            "medical — острое состояние тела; none — риска нет"
        )
    )
    safety_reason: str = Field(
        default="нет",
        max_length=200,
        description="Одна строка на русском, почему выбран уровень, или 'нет'",
    )
    next_action: str = Field(
        default="нет",
        max_length=120,
        description="Что предложить дальше — урок, практика, запись показателей, или 'нет'",
    )
    memory_candidates: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Устойчивые факты о пациенте, или пустой список. Решение о записи принимает не модель",
    )

    @field_validator("safety_kind", mode="before")
    @classmethod
    def _normalize_safety_kind(cls, value: object) -> object:
        """Пустая строка от модели означает «риска нет».

        Когда риска нет, GigaChat присылает ``safety_kind: ""`` вместо ``none``
        — на замере это уронило валидацию 64 раза и увело 15 ходов из 16 на
        откат к старой ветке. Перечисление в схеме оставляем: оно подсказывает
        модели верные значения. Здесь только подчищаем пустоту.
        """
        if value is None:
            return "none"
        if isinstance(value, str) and not value.strip():
            return "none"
        return value
