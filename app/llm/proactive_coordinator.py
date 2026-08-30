"""Единый координатор проактивных сообщений (Фаза 2, каркас).

Раньше три подсистемы работали независимо и каждая сама доставляла:

- ``morning_service``  — утренний дайджест (шаблон), cron 08:00 + вход;
- ``proactive``        — очередь по аномалиям/доменам (LLM), cron 08:05/14/20;
- ``motivator``        — простой по доменам (шаблон), cron 19:00 + вход.

Общего потолка на день не было, дедуп у каждой свой (по
``chat_messages.request_type``), тема могла повториться (утро упомянуло
лекарства + мотиватор прислал «давно не отмечали лекарства»).

Координатор превращает их в **генераторов кандидатов**:

    collect_candidates() → select_candidates() → deliver_selected()
        собрать поводы      ранжировать+дедуп       записать ≤cap штук

Ранжирование (из спеки): кризис → аномалия → пропуски → простой → похвала.
Единый дедуп — таблица ``llm.proactive_deliveries`` (ключ повода + дата) плюс
мосты ``_is_morning_sent_today`` / ``_was_motivator_sent_today``.
Единый потолок — ``DEFAULT_DAILY_CAP`` сообщений на пациента в день.

Точки входа: ``scheduler`` (3 cron-прохода, ``allow_llm=True``) и
``on_login.run_login_proactive`` (``trigger="login"``, ``allow_llm=False`` —
генерацию в момент входа не запускаем). Старые ``deliver_*`` пока живут как
запасной путь; снести после smoke на staging.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Literal
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import ChatMessage, ProactiveDelivery

logger = logging.getLogger("gpt-support-llm.proactive_coordinator")

# Дата дня — по МСК, как в morning_service (ensure_morning_message /
# _upsert_daily_context). Общий дедуп по дню обязан жить в одном поясе, иначе
# около полуночи «сегодня» у координатора и у утреннего сервиса разъедутся.
_MOSCOW_TZ = ZoneInfo("Europe/Moscow")


def _today() -> date:
    return datetime.now(tz=_MOSCOW_TZ).date()


Trigger = Literal["login", "cron_morning", "cron_afternoon", "cron_evening"]

# Потолок проактивных сообщений на пациента в день — суммарно по всем поводам.
DEFAULT_DAILY_CAP = 2

# Ранжирование поводов. Меньше = важнее. Кризис всегда проходит; похвала —
# только если осталось место под потолком и день пустой.
_KIND_PRIORITY: dict[str, int] = {
    "crisis": 0,   # CRITICAL-аномалия → SAFETY-протокол
    "anomaly": 1,   # WARNING-аномалия
    "misses": 2,   # утренний дайджест с невыполненными задачами
    "idle": 3,      # простой активности по домену (мотиватор)
    "domain": 3,    # плохой доменный score (proactive)
    "praise": 4,    # серия/позитивная аналитика недели
}

Kind = Literal["crisis", "anomaly", "misses", "idle", "domain", "praise"]


@dataclass(slots=True)
class ProactiveCandidate:
    """Один повод обратиться к пациенту, ещё не решено — отправим ли."""

    kind: Kind
    dedup_key: str                       # 'morning' | 'anomaly:systolic_bp' | 'idle:sleep'
    trigger_reason: str                  # человекочитаемо, для лога
    domain: str | None = None            # для правила «один повод на домен»
    # Шаблонный повод несёт готовый текст. LLM-повод несёт промпт + роутинг,
    # текст генерирует пайплайн при доставке. Ровно одно из двух.
    text: str | None = None
    buttons: list[dict] | None = None
    request_type: str = "proactive"      # ChatMessage.request_type
    llm_prompt: str | None = None
    router_result: object | None = None  # app.llm.router.RouterResult для LLM-повода
    # Только для morning-повода: дневной контекст, который после доставки надо
    # положить в llm.patient_daily_context (его читает get_daily_context_for_llm).
    daily_context_json: dict | None = None

    @property
    def priority(self) -> int:
        return _KIND_PRIORITY.get(self.kind, 99)

    @property
    def needs_llm(self) -> bool:
        return self.llm_prompt is not None


# --------------------------------------------------------------------------- #
# Выбор: ранжирование + дедуп + потолок  (чистая функция — легко тестировать)
# --------------------------------------------------------------------------- #

def select_candidates(
    candidates: list[ProactiveCandidate],
    *,
    already_sent_keys: set[str],
    cap: int = DEFAULT_DAILY_CAP,
    allow_llm: bool = True,
) -> list[ProactiveCandidate]:
    """Отобрать до ``cap`` кандидатов на отправку.

    Правила:
      1. пропускаем повод, чей ``dedup_key`` уже отправлен сегодня;
      2. ``allow_llm=False`` — отбрасываем поводы, требующие генерации
         (вход пациента: фоновая LLM-генерация упирается в лимит GigaChat,
         cron-джоба разберёт их следующим заходом);
      3. сортируем по приоритету (кризис → … → похвала);
      4. жадно берём сверху, пока не упёрлись в ``cap``;
      5. не берём второй повод по тому же домену (домен уже закрыт более
         важным поводом — второе сообщение про сон подряд лишнее);
      6. кризис проходит всегда, даже сверх потолка — безопасность вперёд.
    """
    fresh = [c for c in candidates if c.dedup_key not in already_sent_keys]
    if not allow_llm:
        fresh = [c for c in fresh if not c.needs_llm]
    fresh.sort(key=lambda c: (c.priority, c.dedup_key))

    selected: list[ProactiveCandidate] = []
    claimed_domains: set[str] = set()
    seen_keys: set[str] = set()
    normal_count = 0  # потолок считаем без кризиса — тот проходит всегда

    for cand in fresh:
        if cand.dedup_key in seen_keys:
            continue
        is_crisis = cand.kind == "crisis"
        if not is_crisis and normal_count >= cap:
            continue
        if cand.domain and cand.domain in claimed_domains and not is_crisis:
            continue

        selected.append(cand)
        seen_keys.add(cand.dedup_key)
        if cand.domain:
            claimed_domains.add(cand.domain)
        if not is_crisis:
            normal_count += 1

    return selected


# --------------------------------------------------------------------------- #
# Сбор кандидатов от подсистем-генераторов
# --------------------------------------------------------------------------- #

async def collect_candidates(
    patient_id: int,
    db: AsyncSession,
    *,
    trigger: Trigger,
) -> list[ProactiveCandidate]:
    """Опросить все подсистемы и собрать поводы. Ни одна не должна ронять сбор."""
    from app.llm.domain_scorer import has_tracked_data

    candidates: list[ProactiveCandidate] = []

    # Аномалии и утренний дайджест — всегда (дайджест сам отдаёт приветствие при
    # холодном старте). Простой и доменные нуджи — только если пациент уже что-то
    # начал: «давно не отмечали сон» человеку, который ещё ничего не отмечал, —
    # это сообщение «из ничего».
    sources = [_anomaly_candidates, _morning_candidate]
    try:
        if await has_tracked_data(patient_id, db):
            sources += [_motivator_candidate, _domain_score_candidates]
    except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
        logger.warning("[coordinator] has_tracked_data failed patient=%d: %s", patient_id, exc)

    for source in sources:
        try:
            candidates.extend(await source(patient_id, db))
        except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
            logger.warning(
                "[coordinator] source=%s failed patient=%d: %s",
                source.__name__, patient_id, exc,
            )

    return candidates


_ANOMALY_LABELS = {
    "systolic_bp": lambda v: f"давление {int(v)} мм рт.ст.",
    "pulse": lambda v: f"пульс {int(v)} уд/мин",
    "weight_gain": lambda v: f"прибавка веса +{v:.1f} кг",
}


def _crisis_anomaly_text(label: str) -> str:
    """Фиксированный текст на кризисную аномалию — как в data_entry.BP_CRITICAL_REPLY.

    Не генерация: разночтения в таком сообщении опаснее его сухости, и оно
    должно доходить сразу при входе, не дожидаясь cron с LLM.
    """
    return (
        f"В твоих записях — {label}. Это заметно выше нормы.\n\n"
        "Отдохни несколько минут сидя и перемерь на той же руке. "
        "Если цифры повторятся — свяжись со своим диализным центром и скажи о них."
    )


async def _anomaly_candidates(patient_id: int, db: AsyncSession) -> list[ProactiveCandidate]:
    from app.llm.anomaly import check_anomalies
    from app.llm.proactive import _make_anomaly_message

    out: list[ProactiveCandidate] = []
    for alert in await check_anomalies(patient_id, db):
        if alert.severity == "CRITICAL":
            label = _ANOMALY_LABELS.get(alert.type, lambda v: f"{alert.type}={v}")(alert.value)
            out.append(
                ProactiveCandidate(
                    kind="crisis",
                    dedup_key=f"anomaly:{alert.type}",
                    trigger_reason=f"CRITICAL anomaly: {alert.type}={alert.value}",
                    domain=alert.domain_hint,
                    request_type="safety",
                    text=_crisis_anomaly_text(label),   # шаблон — доходит и на login
                )
            )
            continue
        msg = _make_anomaly_message(patient_id, alert)
        out.append(
            ProactiveCandidate(
                kind="anomaly",
                dedup_key=f"anomaly:{alert.type}",
                trigger_reason=msg.trigger_reason,
                domain=alert.domain_hint,
                request_type="proactive",
                llm_prompt=msg.user_input,
                router_result=msg.router_result,
            )
        )
    return out


async def _morning_candidate(patient_id: int, db: AsyncSession) -> list[ProactiveCandidate]:
    from app.llm.morning_service import (
        _is_morning_sent_today,
        build_daily_context,
        build_morning_message,
    )

    today = _today()
    # Второй дедуп поверх леджера: «утро сегодня уже отправлено» по
    # patient_daily_context.message_sent — ловит и случай, когда старый путь
    # (deliver_morning_message) ещё где-то остался, и рассинхрон леджера.
    if await _is_morning_sent_today(patient_id, today, db):
        return []

    ctx = await build_daily_context(patient_id, today, db)
    msg = build_morning_message(ctx)

    # Холодный старт: дайджест уже отдал приветствие вместо разбора — не помечаем
    # это «пропусками», иначе координатор поставит поводу высокий приоритет.
    cold = not ctx.get("has_history", True)
    has_misses = not cold and (
        bool(ctx.get("missed_yesterday")) or int(ctx.get("morning_meds_pending", 0) or 0) > 0
    )
    focus = None if cold else ctx.get("focus_topic")
    # focus_topic живёт в терминах доменов дайджеста; сводим к общему словарю
    domain = {"sleep": "sleep", "medication": "medications", "routine": "routine"}.get(focus)

    return [
        ProactiveCandidate(
            kind="misses" if has_misses else "praise",
            dedup_key="morning",
            trigger_reason=f"morning digest (misses={has_misses}, focus={focus})",
            domain=domain,
            text=msg["text"],
            buttons=msg["buttons"] or None,
            request_type="morning",
            daily_context_json=ctx,
        )
    ]


async def _domain_score_candidates(patient_id: int, db: AsyncSession) -> list[ProactiveCandidate]:
    """Домены с плохим score (< 0.5) → LLM-повод мягко спросить о самочувствии.

    Тот же сигнал, что у `proactive.generate_daily_queue`, но кандидатом:
    ранжирование и потолок теперь за координатором.
    """
    from app.llm.domain_scorer import calculate_domain_scores, get_priority_domains
    from app.llm.proactive import _make_domain_message

    scores = await calculate_domain_scores(patient_id, db)
    out: list[ProactiveCandidate] = []
    for domain in get_priority_domains(scores):
        score = scores.get(domain)
        if score is None or score >= 0.5:
            continue
        msg = _make_domain_message(patient_id, domain, score)
        out.append(
            ProactiveCandidate(
                kind="domain",
                dedup_key=f"domain:{domain}",
                trigger_reason=msg.trigger_reason,
                domain=domain,
                request_type="proactive",
                llm_prompt=msg.user_input,
                router_result=msg.router_result,
            )
        )
    return out


async def _motivator_candidate(patient_id: int, db: AsyncSession) -> list[ProactiveCandidate]:
    from app.llm.domain_scorer import get_last_activity_dates
    from app.llm.motivator import (
        _build_motivator_message,
        _was_motivator_sent_today,
        detect_inactivity,
    )

    # Второй дедуп поверх леджера: мотиватор сегодня уже был (по chat_messages).
    if await _was_motivator_sent_today(patient_id, db):
        return []

    last_activity = await get_last_activity_dates(patient_id, db)
    inactive = detect_inactivity(last_activity, _today())
    if not inactive:
        return []

    top = inactive[0]
    msg = _build_motivator_message(top["domain"], top["days"])
    return [
        ProactiveCandidate(
            kind="idle",
            dedup_key=f"idle:{top['domain']}",
            trigger_reason=f"inactivity {top['domain']} {top['days']}d",
            domain=top["domain"],
            text=msg["text"],
            buttons=msg["buttons"] or None,
            request_type="motivator",
        )
    ]


# --------------------------------------------------------------------------- #
# Дедуп-леджер: что уже отправлено пациенту сегодня
# --------------------------------------------------------------------------- #

async def sent_keys_today(db: AsyncSession, patient_id: int, *, today: date | None = None) -> set[str]:
    today = today or _today()
    rows = await db.execute(
        select(ProactiveDelivery.dedup_key).where(
            ProactiveDelivery.patient_id == patient_id,
            ProactiveDelivery.context_date == today,
        )
    )
    return set(rows.scalars().all())


# --------------------------------------------------------------------------- #
# Доставка
# --------------------------------------------------------------------------- #

async def deliver_selected(
    patient_id: int,
    db: AsyncSession,
    selected: list[ProactiveCandidate],
    *,
    trigger: Trigger,
    today: date | None = None,
) -> list[ChatMessage]:
    """Записать отобранные сообщения + строки дедуп-леджера.

    Коммит после каждого повода: сообщения независимы, и сбой на одном
    (например, LLM-генерация упала) не должен терять уже записанные и не должен
    оставлять сессию в rollback-состоянии для следующего.
    """
    today = today or _today()
    written: list[ChatMessage] = []

    for cand in selected:
        try:
            content = cand.text
            model_used = None
            tokens = 0
            if cand.needs_llm:
                content, model_used, tokens = await _render_via_pipeline(patient_id, db, cand)
            if not content:
                continue

            msg = ChatMessage(
                patient_id=patient_id,
                role="assistant",
                content=content,
                tokens_used=tokens,
                model_used=model_used,
                domain=cand.domain,
                request_type=cand.request_type,
                is_read=False,
                buttons_json=cand.buttons,
            )
            db.add(msg)
            await db.flush()

            db.add(
                ProactiveDelivery(
                    patient_id=patient_id,
                    context_date=today,
                    kind=cand.kind,
                    dedup_key=cand.dedup_key,
                    domain=cand.domain,
                    trigger=trigger,
                    message_id=msg.id,
                )
            )

            # morning-повод: дневной контекст в llm.patient_daily_context —
            # его читает get_daily_context_for_llm (SupervisorStage).
            if cand.daily_context_json is not None:
                from app.llm.morning_service import _upsert_daily_context

                await _upsert_daily_context(
                    patient_id, today, cand.daily_context_json, msg.id, db
                )

            await db.commit()
            written.append(msg)
            logger.info(
                "[coordinator] delivered patient=%d key=%s kind=%s trigger=%s",
                patient_id, cand.dedup_key, cand.kind, trigger,
            )
        except (SQLAlchemyError, ValueError, TypeError, KeyError) as exc:
            await db.rollback()
            logger.error(
                "[coordinator] deliver failed patient=%d key=%s: %s",
                patient_id, cand.dedup_key, exc,
            )

    return written


async def _render_via_pipeline(
    patient_id: int, db: AsyncSession, cand: ProactiveCandidate
) -> tuple[str, str | None, int]:
    """LLM-повод (аномалия/домен) → текст через пайплайн.

    TODO(Фаза 2): проактивная генерация упирается в лимит GigaChat (один ключ,
    конкурентность = 1, см. SPRINT1_INVESTIGATIONS.md §1). До «Ограничения
    нагрузки» звать это только из cron-джоб с семафором = 1, не из ``login``.
    """
    from app.llm.pipeline import LLMRequest
    from app.llm.proactive import _llm_pipeline

    resp = await _llm_pipeline.process(
        LLMRequest(
            patient_id=patient_id,
            user_input=cand.llm_prompt or "",
            source="system",
            router_result=cand.router_result,
            db=db,
        )
    )
    return resp.response, resp.model, (resp.tokens_input + resp.tokens_output)


# --------------------------------------------------------------------------- #
# Оркестрация
# --------------------------------------------------------------------------- #

async def run_proactive_coordination(
    patient_id: int,
    db: AsyncSession,
    *,
    trigger: Trigger,
    cap: int = DEFAULT_DAILY_CAP,
    allow_llm: bool | None = None,
    today: date | None = None,
) -> list[ChatMessage]:
    """collect → select → deliver. Возвращает записанные сообщения.

    ``allow_llm`` по умолчанию False для ``trigger="login"`` (фоновая генерация в
    момент входа упирается в лимит GigaChat — cron разберёт следующим заходом) и
    True для cron-джоб.
    """
    today = today or _today()
    if allow_llm is None:
        allow_llm = trigger != "login"

    already = await sent_keys_today(db, patient_id, today=today)
    candidates = await collect_candidates(patient_id, db, trigger=trigger)
    selected = select_candidates(
        candidates, already_sent_keys=already, cap=cap, allow_llm=allow_llm
    )

    if not selected:
        logger.info("[coordinator] patient=%d trigger=%s — нечего отправлять", patient_id, trigger)
        return []

    return await deliver_selected(patient_id, db, selected, trigger=trigger, today=today)
