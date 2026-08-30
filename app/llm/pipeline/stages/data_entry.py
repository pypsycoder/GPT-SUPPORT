"""
Data Entry Stage — запись показателей без обращения к модели.

Каждое пятое сообщение реального пациента это «давление 125 на 85» или «вес 70».
На разметке 104 сообщений `data_entry` набрал 20%, и обе ветки диалога на нём
промахиваются: старая зовёт education-эксперта, агент отвечает как на болтовню.
Разбирать такое моделью незачем — L0 уже вытащил числа регуляркой.

Стадия срабатывает только когда L0 уверенно сказал `data_entry`, то есть числа
разобраны и это не вопрос о норме. Во всех остальных случаях молча пропускает
ход дальше.

Запись в карту делает роутер: pipeline готовит `pending_vitals`, commit остаётся
в слое роутера, как требует CLAUDE.md.
"""

from __future__ import annotations

import logging
import time

from app.llm.pipeline.types import PipelineContext, PipelineStage
from app.llm.router_l0 import BP_DIASTOLIC_HIGH, BP_SYSTOLIC_HIGH

logger = logging.getLogger("gpt-support-llm.pipeline.data_entry")

# Шаблон на кризисные цифры. Фиксированный текст, а не генерация: разночтения
# в таком ответе опаснее, чем его сухость.
BP_CRITICAL_REPLY = (
    "Записал: {value}. Это заметно выше нормы.\n\n"
    "Отдохни пять минут сидя и перемерь давление на той же руке. "
    "Если цифры повторятся — свяжись со своим диализным центром и скажи о них."
)

_LABELS = {
    "BP": "давление",
    "PULSE": "пульс",
    "WEIGHT": "вес",
    "WATER": "вода",
}

# Ответ на отчёт о длительности сна («спал 4 часа»). Записать как есть нельзя —
# схема сна требует время отхода ко сну и подъёма, — поэтому не «Записал», а
# короткая реплика с кнопкой в трекер сна.
SLEEP_ENTRY_REPLY = (
    "Про сон лучше отметить в трекере — там указываешь, во сколько лёг и встал "
    "и как спалось. Так запись будет точной."
)
SLEEP_ENTRY_BUTTONS = [{"label": "Внести данные о сне", "action": "open_sleep"}]


def _render_value(item: dict) -> str:
    kind = item.get("type")
    if kind == "BP":
        return f"{item['systolic']}/{item['diastolic']}"
    value = item.get("value")
    if kind == "WATER":
        return f"{int(value)} мл"
    if kind == "WEIGHT":
        return f"{value} кг"
    return str(value)


def _bp_comment(item: dict) -> str:
    """Короткий комментарий по числам. Без модели и без диагнозов."""
    systolic, diastolic = int(item["systolic"]), int(item["diastolic"])
    if systolic >= BP_SYSTOLIC_HIGH or diastolic >= BP_DIASTOLIC_HIGH:
        return "Выше обычного."
    if systolic < 100 or diastolic < 60:
        return "Ниже обычного."
    return "Это в пределах нормы."


def build_reply(vitals: list[dict], alert: str | None) -> str:
    """Текст пациенту. Комментарий только там, где он однозначен по числам."""
    rendered = ", ".join(f"{_LABELS.get(i['type'], i['type'])} {_render_value(i)}" for i in vitals)

    if alert == "bp_critical":
        bp = next((i for i in vitals if i["type"] == "BP"), None)
        return BP_CRITICAL_REPLY.format(value=_render_value(bp) if bp else rendered)

    comment = ""
    bp = next((i for i in vitals if i["type"] == "BP"), None)
    if bp is not None:
        comment = " " + _bp_comment(bp)
    return f"Записал: {rendered}.{comment}"


class DataEntryStage(PipelineStage):
    @property
    def stage_name(self) -> str:
        return "data_entry"

    async def process(self, context: PipelineContext) -> PipelineContext:
        started = time.monotonic()
        decision = context.l0

        if decision is not None and decision.intent == "sleep_entry":
            context.early_response = SLEEP_ENTRY_REPLY
            context.early_response_source = "sleep_entry"
            context.early_response_buttons = [dict(b) for b in SLEEP_ENTRY_BUTTONS]
            context.diagnostics["data_entry"] = {
                "triggered": True,
                "kind": "sleep_entry",
                "latency_ms": int((time.monotonic() - started) * 1000),
            }
            logger.info("[data_entry] patient=%d — сон: кнопка в трекер, без записи", context.request.patient_id)
            return context

        if decision is None or not decision.vitals:
            context.diagnostics["data_entry"] = {"triggered": False, "reason": "nothing_parsed"}
            return context

        if decision.intent != "data_entry":
            # Показатели есть, но ход не сводится к записи: «давление 200 на 100,
            # мне очень страшно». Цифры сохраняем, а отвечать оставляем модели —
            # сухой шаблон на такое сообщение проигнорировал бы главное.
            # Вопрос о норме («129 на 89 это норма?») не записываем: человек
            # спрашивает, а не отчитывается.
            if decision.rule == "vitals_with_emotion":
                context.pending_vitals = [dict(item) for item in decision.vitals]
            context.diagnostics["data_entry"] = {
                "triggered": False,
                "reason": decision.rule or "not_data_entry",
                "recorded_anyway": bool(context.pending_vitals),
            }
            return context

        context.pending_vitals = [dict(item) for item in decision.vitals]
        context.early_response = build_reply(decision.vitals, decision.alert)
        context.early_response_source = "data_entry"
        context.diagnostics["data_entry"] = {
            "triggered": True,
            "vitals": context.pending_vitals,
            "alert": decision.alert,
            "latency_ms": int((time.monotonic() - started) * 1000),
        }
        logger.info(
            "[data_entry] patient=%d записано без LLM: %s alert=%s",
            context.request.patient_id,
            context.pending_vitals,
            decision.alert,
        )
        return context
