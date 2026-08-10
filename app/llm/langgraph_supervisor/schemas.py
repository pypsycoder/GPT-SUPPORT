"""Pydantic-схемы карточек Graph v2 для структурного вывода GigaChat.

Схемы плоские: только строки и ``Literal`` — никаких вложенных моделей и Enum,
которые Pydantic вынес бы в ``$defs`` + ``$ref`` и сломал бы strict-режим.

Имена полей — русские алиасы, ровно те же, что в текстовых карточках. Это не
косметика: системные промпты и все правила в них написаны через «Готово к
передаче», «Шаг сейчас», «CTA lesson_code». Сохранив имена, мы меняем только
транспорт (текст → JSON), а не семантику, и переиспользуем существующие
``parse_*_card`` / ``validate_*_card`` без дублирования бизнес-правил.

``fields_from_model()`` отдаёт тот же ``dict[str, str]``, который раньше
возвращал ``policy._parse_field_block()``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class _CardSchema(BaseModel):
    """База: запрещаем лишние поля и разрешаем заполнение по имени атрибута."""

    model_config = ConfigDict(populate_by_name=True, extra="forbid")


class IntakeCardSchema(_CardSchema):
    problem: str = Field(alias="Проблема", description="Главная проблема или 'не обозначена'")
    context: str = Field(
        alias="Контекст",
        description="2-3 коротких утверждения фактами или 'контекст пока не раскрыт'",
    )
    ready_to_delegate: Literal["да", "нет"] = Field(alias="Готово к передаче")
    needs_clarification: Literal["да", "нет"] = Field(alias="Нужно уточнение")
    question: str = Field(alias="Вопрос", description="Один вопрос или 'нет'")
    rationale: str = Field(alias="Обоснование", description="Одна короткая строка")


class DelegationCardSchema(_CardSchema):
    expert: Literal["эмоциональная_поддержка", "education"] = Field(alias="Эксперт")
    task: str = Field(alias="Задача", description="Что должен сделать эксперт")
    rationale: str = Field(alias="Обоснование", description="Одна короткая строка")


class EmotionalExpertCardSchema(_CardSchema):
    support: str = Field(alias="Поддержка", description="3-5 слов живой эмпатии или '—'")
    effectiveness: Literal["хорошо", "частично", "не_помогло", "нет_данных"] = Field(alias="Оценка")
    strategy: Literal["углубить", "сменить_подход", "завершить", "продолжить"] = Field(alias="Стратегия")
    mode: Literal["уточнить", "интервенция"] = Field(alias="Режим")
    step_now: str = Field(alias="Шаг сейчас", description="Техника с механизмом или 'нет'")
    follow_up: str = Field(alias="Вопрос пациенту", description="Вопрос или 'нет'")
    branch: Literal["открыть", "продолжить", "закрыть", "нет"] = Field(alias="Ветка")
    branch_type: Literal["отражение", "рефрейм", "возражение", "новая_тема", "нет"] = Field(
        alias="Тип ветки"
    )
    branch_return_intent: str = Field(
        alias="Возврат к протоколу", description="Одно предложение или 'нет'"
    )
    session_plan: str = Field(
        alias="План на следующий ход", description="Одно предложение — что планируешь дальше"
    )
    rationale: str = Field(alias="Обоснование", description="Одна строка")


class EducationExpertCardSchema(_CardSchema):
    explanation: str = Field(
        alias="Ответ", description="3-5 предложений строго по переданным фрагментам"
    )
    follow_up: str = Field(
        alias="Вопрос", description="Предложение узнать больше («Хочешь узнать...?») или 'нет'"
    )
    cta_type: Literal["lesson", "none"] = Field(alias="CTA тип")
    cta_label: str = Field(alias="CTA заголовок", description="Название урока или 'нет'")
    cta_lesson_code: str = Field(alias="CTA lesson_code", description="lesson_code или 'нет'")
    session_plan: str = Field(
        alias="План", description="Одно предложение — что отвечать при следующем уточнении"
    )
    rationale: str = Field(alias="Обоснование", description="Одна короткая строка")


def _strip_echoed_label(key: str, value: str) -> str:
    """Убирает имя поля, продублированное моделью внутрь значения.

    GigaChat в структурном режиме иногда пишет ``{"Поддержка": "Поддержка: -"}``.
    В текстовом режиме это съедал ``_parse_field_block`` — он резал строку по
    первому двоеточию. В JSON резать нечего, и метка доезжала до пациента.
    """
    text = value.strip()
    prefix = f"{key}:"
    if text.lower().startswith(prefix.lower()):
        return text[len(prefix):].strip()
    return text


def fields_from_model(card: BaseModel) -> dict[str, str]:
    """Схема → ``dict`` с русскими ключами, как отдавал ``_parse_field_block``."""
    return {
        key: _strip_echoed_label(key, str(value))
        for key, value in card.model_dump(by_alias=True).items()
    }
