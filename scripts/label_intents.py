"""
Разметка интентов на реальных сообщениях из llm.chat_messages.

Зачем: точность распознавания интента сейчас нечем измерить. Есть только факт,
что старая и новая ветки расходятся, но какая из них права — неизвестно.
Скрипт делает размеченный набор, на котором можно построить confusion matrix
и собрать прототипы для kNN-уровня каскадного роутера (шаг 6).

Что делает:
  * тянет уникальные user-сообщения из llm.chat_messages;
  * размечает каждое отдельным структурным вызовом на max-тире;
  * рядом кладёт вердикт текущего keyword-роутера (бесплатно);
  * помечает строки, которые стоит проверить руками: низкая уверенность
    разметчика либо расхождение с роутером.

Разметчик — не истина в последней инстанции. Он даёт черновик, а на ручную
проверку остаётся небольшой срез вместо всего набора.

Запуск:
    python scripts/label_intents.py [--limit 120] [--out путь.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.core.config import load_environment

load_environment()

from app.llm.pool import pool  # noqa: E402
from app.llm.router import classify_request  # noqa: E402
from core.db.session import async_session_factory  # noqa: E402

DEFAULT_OUT = ROOT_DIR / "LLM_test" / "cases" / "intent_labels.json"

# Таксономия шире, чем у веток: в реальном трафике много записи показателей,
# а ни одна из веток такого интента не знает. Это само по себе находка.
Intent = Literal[
    "emotional_support",
    "education",
    "smalltalk",
    "data_entry",
    "safety",
    "other",
]

LABELER_KEYS = "intent, confidence, rationale"

LABELER_SYSTEM_PROMPT = (
    "Ты размечаешь сообщения пациента на программном гемодиализе, адресованные "
    "боту психологической поддержки. Нужно определить, что человеку нужно "
    "в ответ на ЭТО сообщение.\n"
    "\n"
    "Категории:\n"
    "- emotional_support: говорит о чувствах, страхе, усталости, бессилии, "
    "одиночестве. Даже если попутно упоминает медицинский факт — если ведущее "
    "тут переживание, это emotional_support.\n"
    "- education: фактический вопрос (можно ли, почему, что такое, нормально ли, "
    "сколько), просьба объяснить или посоветовать материал.\n"
    "- smalltalk: приветствие, благодарность, короткое подтверждение "
    "(«да», «ок», «давай», «понятно»), реплика без собственного содержания.\n"
    "- data_entry: сообщает показатель для записи — давление, вес, пульс, "
    "объём жидкости, сон. Даже если рядом есть вопрос о норме, при явном "
    "намерении записать это data_entry.\n"
    "- safety: признаки угрозы жизни, мысли о смерти или самоповреждении, "
    "отказ от жизненно необходимого лечения.\n"
    "- other: не подходит ни под одну категорию.\n"
    "\n"
    "confidence: high — категория очевидна; medium — есть разумная вторая "
    "трактовка; low — сообщение слишком короткое или двусмысленное без контекста.\n"
    "Короткие ответы вроде «да» вне контекста почти всегда smalltalk с "
    "confidence low: без предыдущей реплики бота их намерение не восстановить.\n"
    "\n"
    "Верни ОДИН JSON-объект строго по схеме, без markdown и без пояснений.\n"
    f"Ключи объекта ровно такие, все обязательны: {LABELER_KEYS}."
)


class IntentLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Intent = Field(description="Категория намерения")
    confidence: Literal["high", "medium", "low"] = Field(description="Уверенность разметчика")
    rationale: str = Field(max_length=200, description="Одна короткая строка, почему")


async def fetch_messages(limit: int) -> list[str]:
    async with async_session_factory() as session:
        result = await session.execute(
            text(
                """
                SELECT DISTINCT btrim(content) AS c
                FROM llm.chat_messages
                WHERE role = 'user' AND btrim(content) <> ''
                ORDER BY 1
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return [row[0] for row in result.all()]


async def label_one(message: str) -> IntentLabel | None:
    try:
        client = await pool.get_available("max", allow_fallback=True)
        result = await client.structured(
            [{"role": "user", "content": f"<сообщение>\n{message}\n</сообщение>\n\nРазметь его."}],
            LABELER_SYSTEM_PROMPT,
            IntentLabel,
            temperature=0.0,
            step="intent_label",
            # Системный промпт константный — весь префикс уходит в общий кэш,
            # каждая следующая разметка почти бесплатна.
            session_id="intent-labeler-shared",
            max_tokens=300,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"  ! не размечено: {type(exc).__name__}: {exc}")
        return None
    return result.parsed


def router_verdict(message: str) -> str:
    return classify_request(message, "text").request_type.value


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    messages = await fetch_messages(args.limit)
    print(f"уникальных сообщений: {len(messages)}")

    rows: list[dict] = []
    for index, message in enumerate(messages, start=1):
        label = await label_one(message)
        if label is None:
            continue
        rows.append(
            {
                "text": message,
                "intent": label.intent,
                "confidence": label.confidence,
                "rationale": label.rationale,
                "router_request_type": router_verdict(message),
            }
        )
        if index % 20 == 0:
            print(f"  {index}/{len(messages)}")

    # Ручной проверки заслуживает не весь набор, а только спорное.
    for row in rows:
        row["needs_review"] = bool(
            row["confidence"] == "low"
            or (row["intent"] == "safety") != (row["router_request_type"] == "safety")
        )

    counts = Counter(r["intent"] for r in rows)
    confidence = Counter(r["confidence"] for r in rows)
    review = sum(1 for r in rows if r["needs_review"])

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps({"labels": rows}, ensure_ascii=False, indent=1), encoding="utf-8"
    )

    print(f"\nразмечено: {len(rows)}")
    print(f"интенты:    {dict(counts)}")
    print(f"уверенность:{dict(confidence)}")
    print(f"на ручную проверку: {review}")
    print(f"файл: {args.out}")


if __name__ == "__main__":
    asyncio.run(main())
