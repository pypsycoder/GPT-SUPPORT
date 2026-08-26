"""
L0 — детерминированный уровень маршрутизации. Ноль вызовов модели.

Отвечает только на то, что обязано быть решено ДО обращения к модели:

  * кризис — меняет путь целиком, постфактум уже поздно;
  * показатели — разбираются регуляркой, модель для этого не нужна;
  * короткий ответ на открытый вопрос — интент задан прошлым ходом, а не текстом.

Во всех остальных случаях возвращает ``intent=None`` и пропускает запрос дальше.
L0 не гадает: неуверенность стоит дешевле ошибки.

Две вещи, которые чинятся здесь по замеру на 104 реальных сообщениях:

  1. ``«У меня давление 200 на 100»`` уходило в SAFETY и получало кризисный
     шаблон про телефон доверия. Высокое давление — клиническая тревога и
     запись показателя, а не психологический кризис. Ответ нужен другой.
  2. ``«я выпил 3 таблетки каптоприла, как-то мне плохо»`` не ловилось вообще
     и уходило по обычному пути на lite.

Про пороги: совпадение поднимает уровень тревоги и никогда не понижает.
Ложное срабатывание стоит одного лишнего осторожного ответа, пропуск —
несопоставимо дороже. Отсюда два уровня: узкие однозначные формулировки дают
``urgent`` и кризисный протокол, широкие — ``concern``, который только
поднимает тир и подсвечивает риск, не подменяя ответ.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("gpt-support-llm.router_l0")

ENV_FLAG = "LLM_ROUTER_L0"

_TRUTHY = frozenset({"1", "true", "yes", "on"})


def l0_enabled() -> bool:
    """Включён ли L0. Выключен — работает прежний поиск по подстрокам."""
    return str(os.getenv(ENV_FLAG, "")).strip().lower() in _TRUTHY

# Порог систолического: гипертонический криз.
BP_SYSTOLIC_CRITICAL = 180
BP_DIASTOLIC_CRITICAL = 110
# Ниже критического, но выше нормы — стоит отметить, но это не тревога.
BP_SYSTOLIC_HIGH = 140
BP_DIASTOLIC_HIGH = 90

# Короче этого и без знака вопроса — реплика без собственного содержания.
SHORT_ANSWER_CHARS = 24


def _p(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE | re.UNICODE)


# Однозначные формулировки суицидального намерения. Границы слов обязательны:
# на поиске подстроки «покончить с этим делом» ловилось как кризис.
_URGENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # --- Прямое называние ---
    # Голое упоминание темы срабатывает без оговорок. На 32 тысячах нейтральных
    # постов ВК это дало 10 ложных, но все они из чужого регистра: пресс-релизы,
    # реклама пабликов, объявления о занятиях по первой помощи. В чате пациента
    # такого не бывает — на 104 реальных сообщениях ложных ноль.
    # Отсекать этот регистр по словам вроде «лекция» или «профилактика» пробовал
    # и откатил: получается дыра. «У нас была лекция про суицид, и я подумал,
    # что тоже хочу» — ровно то сообщение, которое пропускать нельзя.
    (_p(r"\b(суицид|самоубийств)"), "suicidal_intent"),
    # «покончить с этим всем» — кризис, «покончить с этими анализами» — нет.
    # Поэтому объект перечислен явно, а не взят как «с чем угодно».
    (_p(r"\bпоконч(ить|у|им)\s+со?\s+(собой|жизнью|всем\s+этим|этим\s+всем)\b"), "suicidal_intent"),
    (_p(r"\b(хочу|хочется|лучше)\s+(сразу\s+)?(умереть|сдохнуть)\b"), "suicidal_intent"),
    # Основа глагола, а не список форм: «убить», «убью», «убьюсь». Перечисляя
    # формы руками, одну обязательно забудешь — этот же промах уже ловился дважды.
    (_p(r"\b(уб(ить|ью|ьюсь)|прикончить)\s+себя\b|\bсебя\s+(уб(ить|ью)|прикончить)\b"), "suicidal_intent"),
    (_p(r"\bсвести\s+счёты\s+с\s+жизнью\b|\bпрощат?ься\s+с\s+жизнью\b"), "suicidal_intent"),
    (_p(r"\bзаконч(ить|у)\s+(свои\s+)?страдани"), "suicidal_intent"),
    (_p(r"\bне\s+хоч(у|ется)\s+(больше\s+)?жить\b"), "suicidal_intent"),
    (_p(r"\b(не\s+вижу|нет)\s+(больше\s+)?смысла\s+(дальше\s+)?жить\b"), "suicidal_intent"),
    (_p(r"\bуй(ти|ду|дём)\s+из\s+жизни\b"), "suicidal_intent"),
    (_p(r"\bлучше\s+(бы|уж)\b.{0,15}\bумер"), "suicidal_intent"),
    # --- Названный способ. Самый однозначный сигнал из всех ---
    (
        _p(
            r"\b(поре(жу|зать)|режу|резать|вскр(ою|ыть))\s+(себе\s+)?(вены|руки)\b"
            r"|\bпорежусь\b|\b(пойду|иду|буду)\s+резаться\b|\bрезаться\b"
        ),
        "self_harm",
    ),
    # ПРИМЕЧАНИЕ: "self_harm" из этой строки — единственный urgent-паттерн с
    # проверкой на отрицание, см. _SELF_HARM_NEGATED_RE и его использование в
    # classify(). Остальные urgent-паттерны сознательно её не имеют.
    (_p(r"\b(причинить\s+себе\s+вред|навредить\s+себе|порезать\s+себя)\b"), "self_harm"),
    (_p(r"\bповеш(усь|аюсь)\b|\bповесит?ься\b|\bготовлю\s+верёвк"), "suicidal_method"),
    (_p(r"\bсобираюсь\s+(вы)?прыгн"), "suicidal_method"),
    (_p(r"\b(вы)?прыгну(ть|у)\s+(из\s+окна|с\s+балкона|с\s+моста|с\s+крыши)\b"), "suicidal_method"),
    (_p(r"\bнож\w*\s+(уже\s+)?(взял|в\s+рук|остр\w*\s+лежит|лежит\s+перед)"), "suicidal_method"),
    # --- Эвфемизмы завершения. Здесь же самая тонкая граница с concern ---
    (_p(r"\bпоследний\s+шаг\b"), "suicidal_intent"),
    (_p(r"\b(всё|все|это)?\s*законч(ить|у)\s+раз\s+и\s+навсегда\b"), "suicidal_intent"),
    (_p(r"\bпора\s+кончать\s+с\s+(этим|жизнью)"), "suicidal_intent"),
    (_p(r"\bпрощаюсь\s+со\s+всеми\b"), "suicidal_intent"),
)

# Острое медицинское состояние: платформа не лечит, но обязана сказать
# «звони в скорую» вместо разговора о чувствах.
_MEDICAL_URGENT_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # Основа вместо перечисления форм: «потерял», «теряю», «теряет» — всё это
    # одинаково срочно, а перечисляя формы руками, одну обязательно забудешь.
    (_p(r"\b(по)?теря\w*\s+сознание\b|\bсознание\s+(по)?теря\w*\b"), "loss_of_consciousness"),
    (_p(r"\bбез\s+сознания\b"), "loss_of_consciousness"),
    (_p(r"\bне\s+дышит\b"), "not_breathing"),
    (_p(r"\bкровотечени"), "bleeding"),
    (_p(r"\bсудорог"), "seizure"),
    (_p(r"\b(невыносим\w*|нестерпим\w*)\s+бол"), "severe_pain"),
    # --- Лекарства не по назначению ---
    (_p(r"\b(выпил|выпила|принял|приняла)\s+(\d+|все|всю пачку|лишн\w+)\s*таблет"), "overdose"),
    (_p(r"\bпередозировк"), "overdose"),
    (_p(r"\bдвойную\s+дозу\b"), "overdose"),
    (_p(r"\bвместо\s+одной\b|\bне\s+ту\s+таблетк"), "overdose"),
    (_p(r"\bтаблетк\w*\s+(соседк|подруг|жены|мужа|чуж)"), "wrong_medication"),
    (_p(r"\b(проглотил|выпил|приняла?)\w*\s+.{0,20}много\s+таблет"), "overdose"),
    # --- Дыхание и грудь. Для диализного пациента это отдельный красный флаг ---
    # "breathing" — единственное правило здесь с исключением по хроничности,
    # см. _CHRONIC_QUALIFIER_RE и его использование в classify(): у диализного
    # пациента с СН/диабетом одышка при нагрузке — обычный многодневный фон,
    # а не то же самое, что "не могу дышать прямо сейчас".
    (
        _p(
            r"\bзадыхаюсь\b|\bзадохнусь\b|\bнечем\s+дышать\b|\bне\s+могу\s+дышать\b"
            r"|\bдышать\s+(очень\s+)?(тяжело|трудно)\b|\bтяжело\s+дышать\b"
            r"|\bнехватка\s+воздуха\b|\bвоздуха\s+не\s+хватает\b|\bдыхание\s+затруднено\b"
            r"|\bсильная\s+одышка\b"
        ),
        "breathing",
    ),
    (_p(r"\bбол\w*\s+за\s+грудиной\b|\b(давит|сдавливает)\s+(в\s+)?груд|\bбол\w*\s+в\s+груди\b|\bгрудь\s+сдавливает\b"), "chest_pain"),
    # --- Фистула и кровь ---
    (
        _p(
            r"\bпошла\s+кровь\b|\bкров\w*\s+(из|изо)\s+(фистул|рта|носа|руки)"
            r"|\bкровь\s+течёт\b|\bфистула\s+\w*\s*кровит\b|\bкровит\b|\bвырвало\s+кровью\b"
        ),
        "bleeding",
    ),
    (_p(r"\bрука\s+опухла\b"), "access_problem"),
    # --- Общие острые состояния ---
    (_p(r"\bрвота\s*не\s*прекращ|\bнепрекращается\b|\bнеукротим\w*\s+рвот"), "vomiting"),
    (_p(r"\bтемпература\b.{0,20}\b(39|40|сорок)"), "fever"),
    (_p(r"\b(пропало|потерял\w*)\s+зрение\b|\bничего\s+не\s+вижу\b"), "vision_loss"),
    # Скачок давления сам по себе — не срочность (её ловит порог по цифрам),
    # но вместе с тошнотой или головокружением это уже другое дело.
    (_p(r"\bдавлени\w*.{0,45}(тошнит|рвёт|кружится\s+голова|темнеет\s+в\s+глазах)"), "bp_with_symptoms"),
)

# Широкие формулировки истощения. Только повышают тревогу, ответ не подменяют:
# «больше не могу» одинаково часто про усталость и про отчаяние.
_CONCERN_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (_p(r"\bбольше\s+не\s+могу\b"), "exhaustion"),
    (_p(r"\b(не\s+вижу|нет)\s+смысла\b"), "hopelessness"),
    (_p(r"\bвсё\s+бессмысленно\b"), "hopelessness"),
    (_p(r"\bне\s+хочу\s+(на\s+)?диализ\b"), "treatment_refusal"),
    (_p(r"\b(брошу|бросить|откажусь|отказаться)\s+(от\s+)?диализ"), "treatment_refusal"),
    (_p(r"\bруки\s+опускаются\b"), "hopelessness"),
    (_p(r"\bникому\s+не\s+нужен\b"), "isolation"),
)

# Многодневный/нагрузочный фон при "breathing" — не то же самое, что острое
# "не могу дышать прямо сейчас". У СН/ХБП-пациентов одышка при ходьбе —
# рутинный симптом, requiring лечащую команду, а не скорую немедленно.
_CHRONIC_QUALIFIER_RE = _p(
    r"\bособенно\s+когда\b|\bкогда\s+хож\w+\b|\bпри\s+ходьбе\b|\bпри\s+нагрузке\b"
    r"|\bпри\s+физ\w*\s+нагрузк|\bкогда\s+иду\b|\bесли\s+иду\b|\bкогда\s+двига\w+\b"
    r"|\bуже\s+(несколько\s+)?дн\w+\b|\bпоследни\w+\s+дн\w+\b|\bна\s+этой\s+неделе\b"
)

# Второй, независимый путь распознать тот же хронический фон: перечисление
# симптомов не всегда содержит связку "когда"/"при" ("ходить тяжело, сразу
# задыхаюсь" — тоже нагрузочная одышка, просто без явного союза). У СН+ХБП
# пациента отёки и скачущий сахар — тот же кластер, что "одышка при нагрузке"
# в промпте агента (prompts.py, критерий concern) — если оба есть в одном
# сообщении, это рутинное перечисление известных симптомов, а не новое острое
# событие. Не убирает L0 совсем: сообщение всё равно идёт в агента с
# safety_level=concern, у которого есть собственный второй эшелон защиты
# (_apply_agent_safety_net в supervisor.py) на случай, если это перечисление
# всё же маскирует что-то острое.
_EDEMA_RE = _p(r"\bотек\w*|\bопух\w*|\bраздува\w*\s+ног|\bраспух\w*")
_GLUCOSE_FLUX_RE = _p(r"\bсахар\w*.{0,25}(прыга|скач|пляш|мен\w+ся|туда.сюда|то\s+вверх)")


def _is_comorbid_symptom_recital(text: str) -> bool:
    return bool(_EDEMA_RE.search(text) and _GLUCOSE_FLUX_RE.search(text))

# Гипотетический вопрос ("а вдруг", "что если") про медицинский красный флаг —
# не то же самое, что отчёт о том, что происходит прямо сейчас. Найдено на
# patient-sim (s05_anxious): "а вдруг я потеряю сознание и никто не заметит?"
# уходило в тот же кризисный медпротокол, что реальная потеря сознания.
# Применяется только к _MEDICAL_URGENT_PATTERNS — психологические urgent-паттерны
# намеренно читают широко и хуже reflect гипотетичность (см. их комментарий выше).
_HYPOTHETICAL_MARKER_RE = _p(
    r"\bа\s+вдруг\b|\bчто\s+если\b|\bчто\s+будет,?\s+если\b|\bа\s+если\b|\bесли\s+вдруг\b"
)


def _is_hypothetical_question(text: str) -> bool:
    return "?" in text and bool(_HYPOTHETICAL_MARKER_RE.search(text))


# "self_harm" ловит подстроку "навредить себе"/"причинить себе вред" без учёта
# грамматического отрицания прямо перед ней. Найдено на patient-sim
# (s04_non_adherent): "...сколько можно есть и пить, чтобы НЕ навредить
# себе?" — обычный вопрос про диету, не риск. Окно в 2 слова между "не" и
# фразой — намеренно узкое, чтобы не гасить сигнал на "не хочу, но иногда
# так тяжело, что могу навредить себе" (отрицание там относится к "хочу",
# не к самому вреду). Остальные urgent-паттерны (suicidal_intent и т.д.)
# этой проверки не имеют — читают широко по замыслу (см. их комментарий).
_SELF_HARM_NEGATED_RE = _p(
    r"\bне\s+(\w+\s+){0,2}(причинить\s+себе\s+вред|навредить\s+себе|порезать\s+себя)\b"
)

# Показатели. Давление ищем первым: «120 на 80» и «120/80» — одна и та же запись.
_BP_RE = _p(r"\b(\d{2,3})\s*(?:/|\\|\s+на\s+)\s*(\d{2,3})\b")
_PULSE_RE = _p(r"\bпульс\w*\D{0,12}(\d{2,3})\b")
_WEIGHT_RE = _p(r"\bвес\w*\D{0,12}(\d{2,3}(?:[.,]\d)?)\b")
_WATER_RE = _p(r"\b(?:выпил\w*|воды|жидкости)\D{0,12}(\d{3,4})\s*(?:мл|миллилитр)")
_SLEEP_RE = _p(r"\b(?:спал\w*|сон|поспал\w*)\D{0,12}(\d{1,2}(?:[.,]\d)?)\s*час")

# Просьба показать уже записанное — не запись. «Какое моё давление» и
# «давление 120 на 80» отличаются намерением, а не набором цифр.
_DATA_QUERY_RE = _p(
    r"\b(как(ое|ие|ая)|скажи|покажи|напиши|есть\s+ли|у\s+тебя\s+есть)\b.{0,40}"
    r"\b(мо[ёеи]\w*|мои|меня)\b|\bза\s+(прошл\w+|последн\w+|недел\w+)\b"
)


@dataclass(slots=True)
class L0Decision:
    """Решение L0. ``intent=None`` означает «не знаю, разбирайтесь дальше»."""

    intent: str | None = None
    rule: str | None = None
    safety_level: str = "none"          # none | concern | urgent
    safety_kind: str | None = None      # psychological | medical
    vitals: list[dict[str, Any]] = field(default_factory=list)
    alert: str | None = None            # bp_critical | bp_high
    continued_intent: str | None = None

    @property
    def resolved(self) -> bool:
        """Дал ли L0 уверенный ответ."""
        return self.intent is not None


def _match(patterns, text: str) -> str | None:
    for pattern, rule in patterns:
        if pattern.search(text):
            return rule
    return None


def parse_vitals(text: str) -> list[dict[str, Any]]:
    """Разбор показателей регуляркой. Модель для этого не нужна."""
    vitals: list[dict[str, Any]] = []

    match = _BP_RE.search(text)
    if match:
        systolic, diastolic = int(match.group(1)), int(match.group(2))
        # Отсекаем заведомо не-давление: «выпил 2 из 3», годы, диапазоны.
        if 60 <= systolic <= 300 and 30 <= diastolic <= 200 and systolic > diastolic:
            vitals.append({"type": "BP", "systolic": systolic, "diastolic": diastolic})

    for regex, kind, cast in (
        (_PULSE_RE, "PULSE", int),
        (_WEIGHT_RE, "WEIGHT", lambda v: float(str(v).replace(",", "."))),
        (_WATER_RE, "WATER", int),
        (_SLEEP_RE, "SLEEP", lambda v: float(str(v).replace(",", "."))),
    ):
        found = regex.search(text)
        if found:
            vitals.append({"type": kind, "value": cast(found.group(1))})
    return vitals


def _bp_alert(vitals: list[dict[str, Any]]) -> str | None:
    for item in vitals:
        if item.get("type") != "BP":
            continue
        systolic, diastolic = int(item["systolic"]), int(item["diastolic"])
        if systolic >= BP_SYSTOLIC_CRITICAL or diastolic >= BP_DIASTOLIC_CRITICAL:
            return "bp_critical"
        if systolic >= BP_SYSTOLIC_HIGH or diastolic >= BP_DIASTOLIC_HIGH:
            return "bp_high"
    return None


# «Давление 129 на 89 это норма?» — цифры те же, что при записи, но человек
# спрашивает, а не отчитывается. Такое L0 не присваивает никому: пусть решает
# модель, которая поймёт вопрос.
_ASKS_ABOUT_NORM = _p(r"\?|\bнормальн|\bнорма\b|\bэто\s+(ок|нормально)\b|\bстоит\s+ли\b|\bопасно\b")


def _is_question_about_numbers(text: str) -> bool:
    return bool(_ASKS_ABOUT_NORM.search(text))


def _carries_emotion(text: str) -> bool:
    """Есть ли в сообщении переживание помимо цифр.

    Переиспользуем детектор из библиотеки техник — тот же, по которому эксперт
    подбирает упражнение. Он детерминированный и уже выверен: на чистых записях
    вроде «давление 125 на 85» молчит.
    """
    from app.llm.technique_library import infer_emotions  # локально: избегаем цикла импорта

    return bool(infer_emotions(text, ""))


def _is_short_answer(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) > SHORT_ANSWER_CHARS:
        return False
    # Вопрос — это самостоятельное содержание, а не подтверждение.
    return "?" not in stripped


def classify(
    text: str,
    *,
    has_pending_question: bool = False,
    previous_intent: str | None = None,
) -> L0Decision:
    """Детерминированное решение до обращения к модели.

    Порядок правил не случайный: кризис проверяется раньше показателей,
    поэтому «давление 200, теряю сознание» уйдёт в urgent, а «давление 200
    на 100» останется записью показателя с клинической тревогой.
    """
    message = str(text or "").strip()
    if not message:
        return L0Decision()

    rule = _match(_URGENT_PATTERNS, message)
    if rule:
        if rule == "self_harm" and _SELF_HARM_NEGATED_RE.search(message):
            return L0Decision(
                rule="self_harm_negated", safety_level="concern", safety_kind="psychological"
            )
        return L0Decision(intent="safety", rule=rule, safety_level="urgent", safety_kind="psychological")

    rule = _match(_MEDICAL_URGENT_PATTERNS, message)
    if rule:
        # Ни один из этих двух случаев не гасит сигнал совсем — оба поднимают
        # тревогу и явно помечают причину, но не подменяют ответ кризисным
        # протоколом и не обрывают пайплайн: intent=None пропускает запрос
        # дальше (см. boundary_guard.py — short-circuit только на urgent).
        if rule == "breathing" and (
            _CHRONIC_QUALIFIER_RE.search(message) or _is_comorbid_symptom_recital(message)
        ):
            return L0Decision(
                rule="breathing_chronic", safety_level="concern", safety_kind="medical"
            )
        if _is_hypothetical_question(message):
            return L0Decision(
                rule=f"{rule}_hypothetical", safety_level="concern", safety_kind="medical"
            )
        return L0Decision(intent="safety", rule=rule, safety_level="urgent", safety_kind="medical")

    vitals = parse_vitals(message)
    alert = _bp_alert(vitals)
    concern = _match(_CONCERN_PATTERNS, message)

    if _DATA_QUERY_RE.search(message):
        # «Какие у меня цифры за прошлую неделю» — чтение, а не запись.
        # Отдаём модели: показать историю L0 всё равно не может.
        return L0Decision(rule="data_query", safety_level="concern" if concern else "none")

    if vitals:
        safety_level = "concern" if (alert == "bp_critical" or concern) else "none"
        safety_kind = "medical" if alert == "bp_critical" else None
        if _carries_emotion(message):
            # «Давление 200 на 100, мне очень страшно» — цифры записать надо, но
            # отвечать сухим шаблоном нельзя: человек сказал о страхе, и это
            # ровно то, ради чего платформа существует. Показатели отдаём
            # дальше, ответ пишет модель.
            logger.debug("[l0] показатели вместе с эмоцией — интент не присваиваю")
            return L0Decision(
                rule="vitals_with_emotion",
                safety_level=safety_level,
                safety_kind=safety_kind,
                vitals=vitals,
                alert=alert,
            )
        if _is_question_about_numbers(message):
            # Цифры есть, но человек спрашивает, а не записывает. Интент не
            # присваиваем, а разобранные показатели и тревогу отдаём дальше —
            # они пригодятся тому, кто будет отвечать.
            return L0Decision(
                rule="numbers_in_question",
                safety_level=safety_level,
                safety_kind=safety_kind,
                vitals=vitals,
                alert=alert,
            )
        # Показатель — это запись, даже когда цифры высокие. Кризисный шаблон
        # про телефон доверия на «давление 200 на 100» был прямой ошибкой.
        return L0Decision(
            intent="data_entry",
            rule="vitals_parsed",
            safety_level=safety_level,
            safety_kind=safety_kind,
            vitals=vitals,
            alert=alert,
        )

    if concern:
        # Уровень тревоги подняли, но интент не присвоили: пусть решает модель,
        # которая видит контекст. Стоп-слова работают только на повышение.
        return L0Decision(rule=concern, safety_level="concern", safety_kind="psychological")

    if has_pending_question and _is_short_answer(message):
        # «да», «давай», «более-менее» — намерение задано прошлым ходом.
        # Классифицировать такое по тексту невозможно в принципе.
        return L0Decision(
            intent="continuation",
            rule="short_answer_to_pending_question",
            continued_intent=previous_intent,
        )

    return L0Decision()
