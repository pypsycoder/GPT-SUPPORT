"""Конфигурация шкалы приверженности лечению КОП-25 А1."""

from __future__ import annotations

from typing import List


def _build_options(question_id: str, texts: List[str]) -> List[dict]:
    return [
        {"id": f"{question_id}_{idx + 1}", "text": text, "score": idx + 1}
        for idx, text in enumerate(texts)
    ]


IMPORTANCE_OPTIONS = [
    "Совсем не важно",
    "Скорее не важно",
    "Немного важно, но могу отложить",
    "Умеренно важно",
    "Очень важно",
    "Крайне важно, обязательно",
]

DIFFICULTY_OPTIONS = [
    "Совсем не сложно",
    "Почти не сложно",
    "Скорее несложно",
    "Немного сложно",
    "Довольно сложно",
    "Чрезвычайно сложно",
]

READINESS_OPTIONS = [
    "Ни за что не буду",
    "Скорее не буду",
    "Сомневаюсь, скорее нет",
    "Скорее готов(а)",
    "Готов(а) и постараюсь",
    "Обязательно буду выполнять",
]


KOP25A_CONFIG: dict = {
    "code": "KOP25A",
    "version": "1.0",
    "title": "Анкета приверженности лечению КОП-25 А1",
    "questions": [
        {
            "id": "Q1",
            "text": "Насколько важно для вас обсуждать с врачом план лечения и получать регулярные рекомендации?",
            "options": _build_options("Q1", IMPORTANCE_OPTIONS),
            "groups": ["VS"],
        },
        {
            "id": "Q2",
            "text": "Представьте, что лекарство нужно принимать каждый день много лет. Насколько сложно вам будет соблюдать такую рекомендацию?",
            "options": _build_options("Q2", DIFFICULTY_OPTIONS),
            "groups": ["VT"],
        },
        {
            "id": "Q3",
            "text": "Если при приёме препаратов появляются неприятные ощущения, насколько сложно вам будет продолжать приём по назначению?",
            "options": _build_options("Q3", DIFFICULTY_OPTIONS),
            "groups": ["VT"],
        },
        {
            "id": "Q4",
            "text": "Если таблетки нужно принимать несколько раз в день, насколько сложно вам будет не пропускать дозы?",
            "options": _build_options("Q4", DIFFICULTY_OPTIONS),
            "groups": ["VT"],
        },
        {
            "id": "Q5",
            "text": "Насколько важно для вас регулярно сдавать анализы и проходить контрольные обследования по назначению врача?",
            "options": _build_options("Q5", IMPORTANCE_OPTIONS),
            "groups": ["VS"],
        },
        {
            "id": "Q6",
            "text": "Насколько важно для вас принимать лекарства строго в назначенное время?",
            "options": _build_options("Q6", IMPORTANCE_OPTIONS),
            "groups": ["VT"],
        },
        {
            "id": "Q7",
            "text": "Насколько важно для вас соблюдать рекомендации по питанию (ограничение соли, сахара, жиров)?",
            "options": _build_options("Q7", IMPORTANCE_OPTIONS),
            "groups": ["VM"],
        },
        {
            "id": "Q8",
            "text": "Насколько важно для вас увеличить физическую активность по рекомендации врача?",
            "options": _build_options("Q8", IMPORTANCE_OPTIONS),
            "groups": ["VM"],
        },
        {
            "id": "Q9",
            "text": "Насколько важно для вас отказаться от вредных привычек ради лечения?",
            "options": _build_options("Q9", IMPORTANCE_OPTIONS),
            "groups": ["VM"],
        },
        {
            "id": "Q10",
            "text": "Насколько важно сразу сообщать врачам о новых симптомах или изменениях самочувствия?",
            "options": _build_options("Q10", IMPORTANCE_OPTIONS),
            "groups": ["VS"],
        },
        {
            "id": "Q11",
            "text": "Насколько важно посещать консультации медсестры или координатора лечения?",
            "options": _build_options("Q11", IMPORTANCE_OPTIONS),
            "groups": ["VS"],
        },
        {
            "id": "Q12",
            "text": "Насколько важно уделять внимание качеству сна и восстановлению?",
            "options": _build_options("Q12", IMPORTANCE_OPTIONS),
            "groups": ["VM"],
        },
        {
            "id": "Q13",
            "text": "Насколько важно регулярно обсуждать результаты лечения и корректировать план вместе с врачом?",
            "options": _build_options("Q13", IMPORTANCE_OPTIONS),
            "groups": ["VS"],
        },
        {
            "id": "Q14",
            "text": "Насколько важно заранее пополнять запас лекарств, чтобы не пропускать приём?",
            "options": _build_options("Q14", IMPORTANCE_OPTIONS),
            "groups": ["VT"],
        },
        {
            "id": "Q15",
            "text": "Насколько важно планировать ежедневный режим так, чтобы успевать выполнять рекомендации?",
            "options": _build_options("Q15", IMPORTANCE_OPTIONS),
            "groups": ["VM"],
        },
        {
            "id": "Q16",
            "text": "Насколько вы готовы принимать лекарства по назначению каждый день?",
            "options": _build_options("Q16", READINESS_OPTIONS),
            "groups": ["GT", "GS"],
        },
        {
            "id": "Q17",
            "text": "Насколько вы готовы продолжать приём препаратов, даже если не чувствуете мгновенного эффекта?",
            "options": _build_options("Q17", READINESS_OPTIONS),
            "groups": ["GT"],
        },
        {
            "id": "Q18",
            "text": "Насколько вы готовы консультироваться с врачом, прежде чем менять дозировку или пропускать лекарства?",
            "options": _build_options("Q18", READINESS_OPTIONS),
            "groups": ["GT"],
        },
        {
            "id": "Q19",
            "text": "Насколько вы готовы посещать контрольные визиты и делиться информацией о лечении?",
            "options": _build_options("Q19", READINESS_OPTIONS),
            "groups": ["GS", "GM"],
        },
        {
            "id": "Q20",
            "text": "Насколько вы готовы вести дневник приёма лекарств и обсуждать его с врачом?",
            "options": _build_options("Q20", READINESS_OPTIONS),
            "groups": ["GT", "GS"],
        },
        {
            "id": "Q21",
            "text": "Насколько вы готовы заранее организовывать приём лекарств в поездках или при смене графика?",
            "options": _build_options("Q21", READINESS_OPTIONS),
            "groups": ["GT"],
        },
        {
            "id": "Q22",
            "text": "Насколько вы готовы ежедневно следить за питанием и ограничивать соль/сахар ради лечения?",
            "options": _build_options("Q22", READINESS_OPTIONS),
            "groups": ["GM"],
        },
        {
            "id": "Q23",
            "text": "Насколько вы готовы выделять время на регулярную физическую активность?",
            "options": _build_options("Q23", READINESS_OPTIONS),
            "groups": ["GM"],
        },
        {
            "id": "Q24",
            "text": "Насколько вы готовы выполнять назначения по дополнительным обследованиям и реабилитации?",
            "options": _build_options("Q24", READINESS_OPTIONS),
            "groups": ["GS", "GM"],
        },
        {
            "id": "Q25",
            "text": "Насколько вы готовы пользоваться напоминаниями и сообщать врачу обо всех изменениях?",
            "options": _build_options("Q25", READINESS_OPTIONS),
            "groups": ["GS", "GM"],
        },
    ],
}
