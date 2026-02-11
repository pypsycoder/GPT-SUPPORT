from __future__ import annotations

"""Сервисный слой модуля рутины (d230).

Содержит:
- подготовку baseline (закрытие старого, создание нового),
- формирование предзаполненного плана по шаблону и типу дня,
- подготовку данных верификации,
- расчёт дневных метрик d230.
"""

import datetime as dt
from collections.abc import Mapping
from typing import Dict, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.dialysis.service import is_dialysis_day
from app.routine import crud
from app.routine.models import DailyPlan, DailyVerification, compute_retrospective_days
from app.routine.schemas import (
    ActivityCategory,
    ActivityExecution,
    ActivityPlan,
    BaselineRoutineCreate,
    DailyPlanCreate,
    DailyVerificationCreate,
    DailyRoutineMetrics,
)


class RoutineService:
    """Высокоуровневые операции модуля d230."""

    # --- Baseline ---

    @classmethod
    async def upsert_baseline(
        cls,
        session: AsyncSession,
        *,
        patient_id: int,
        payload: BaselineRoutineCreate,
        now: Optional[dt.datetime] = None,
    ):
        """Создать новый baseline, при наличии активного — закрыть его."""
        now = now or dt.datetime.now(dt.timezone.utc)

        active = await crud.get_active_baseline(session, patient_id=patient_id)
        if active is not None:
            await crud.close_active_baseline(session, baseline=active, valid_to=now.date())

        data = {
            "patient_id": patient_id,
            "completed_at": now,
            "activity_pool": payload.activity_pool,
            "dialysis_day_template": payload.dialysis_day_template,
            "non_dialysis_day_template": payload.non_dialysis_day_template,
            "planning_time": payload.planning_time,
            "valid_from": now.date(),
            "valid_to": None,
        }
        return await crud.create_baseline(session, data)

    # --- Планер ---

    @classmethod
    async def get_or_build_plan(
        cls,
        session: AsyncSession,
        *,
        patient_id: int,
        plan_date: dt.date,
    ) -> Tuple[Optional[DailyPlan], Optional[dict]]:
        """Вернуть существующий план или предзаполненный шаблон (без сохранения).

        Возвращает кортеж (plan, template_data). Если plan существует — template_data = None.
        """
        existing = await crud.get_plan_by_date(session, patient_id=patient_id, plan_date=plan_date)
        if existing is not None:
            return existing, None

        baseline = await crud.get_active_baseline(session, patient_id=patient_id)
        if baseline is None:
            return None, None

        dialysis_flag = await is_dialysis_day(session, patient_id=patient_id, date=plan_date)
        template_categories = (
            baseline.dialysis_day_template if dialysis_flag else baseline.non_dialysis_day_template
        )

        # Верхний блок — активности из выбранного шаблона с planned=True
        template_activities: Dict[ActivityCategory, ActivityPlan] = {
            cat: ActivityPlan(planned=True, planned_duration=None)
            for cat in template_categories
        }

        # Активности из пула, не вошедшие в шаблон — planned=False
        added_from_pool: Dict[ActivityCategory, ActivityPlan] = {
            cat: ActivityPlan(planned=False, planned_duration=None)
            for cat in baseline.activity_pool
            if cat not in template_categories
        }

        # Пять пустых слотов для кастомных активностей
        custom_activities = [None, None, None, None, None]

        template_data = {
            "dialysis_day": dialysis_flag,
            "template_activities": {
                k: v.model_dump() for k, v in template_activities.items()
            },
            "added_from_pool": {
                k: v.model_dump() for k, v in added_from_pool.items()
            },
            "custom_activities": custom_activities,
        }
        # #region agent log
        import json as _json
        with open(r"d:\PROJECT\GPT-SUPPORT\.cursor\debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({"location": "routine/service.py:get_or_build_plan", "message": "template_data built", "data": {"template_categories": template_categories, "template_keys": list(template_activities.keys()), "added_keys": list(added_from_pool.keys()), "activity_pool_len": len(baseline.activity_pool)}, "hypothesisId": "H1", "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)}, ensure_ascii=False) + "\n")
        # #endregion
        return None, template_data

    @classmethod
    async def get_template_data(
        cls,
        session: AsyncSession,
        *,
        patient_id: int,
        plan_date: dt.date,
    ) -> Optional[dict]:
        """Построить только template_data из baseline (template_activities, added_from_pool, dialysis_day).
        Возвращает None, если baseline нет. Используется для «дозаполнения» плана с пустыми полями.
        """
        baseline = await crud.get_active_baseline(session, patient_id=patient_id)
        if baseline is None:
            return None
        dialysis_flag = await is_dialysis_day(session, patient_id=patient_id, date=plan_date)
        template_categories = (
            baseline.dialysis_day_template if dialysis_flag else baseline.non_dialysis_day_template
        )
        template_activities = {
            cat: ActivityPlan(planned=True, planned_duration=None).model_dump()
            for cat in template_categories
        }
        added_from_pool = {
            cat: ActivityPlan(planned=False, planned_duration=None).model_dump()
            for cat in baseline.activity_pool
            if cat not in template_categories
        }
        return {
            "dialysis_day": dialysis_flag,
            "template_activities": template_activities,
            "added_from_pool": added_from_pool,
        }

    @classmethod
    async def save_plan(
        cls,
        session: AsyncSession,
        *,
        patient_id: int,
        payload: DailyPlanCreate,
        submitted_at: Optional[dt.datetime] = None,
    ) -> DailyPlan:
        submitted_at = submitted_at or dt.datetime.now(dt.timezone.utc)
        retrospective_days = compute_retrospective_days(submitted_at, payload.plan_date)

        data = {
            "dialysis_day": payload.dialysis_day,
            "template_activities": cls._dump_activities(payload.template_activities),
            "added_from_pool": cls._dump_activities(payload.added_from_pool),
            "custom_activities": cls._dump_custom_activities(payload.custom_activities),
            "retrospective_days": retrospective_days,
        }
        # #region agent log
        import json as _json
        _dta = data.get("template_activities") or {}
        _dap = data.get("added_from_pool") or {}
        with open(r"d:\PROJECT\GPT-SUPPORT\.cursor\debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({"location": "routine/service.py:save_plan", "message": "data for crud", "data": {"template_keys": list(_dta.keys()), "added_keys": list(_dap.keys())}, "hypothesisId": "H4", "timestamp": int(dt.datetime.now(dt.timezone.utc).timestamp() * 1000)}, ensure_ascii=False) + "\n")
        # #endregion
        return await crud.upsert_plan(
            session,
            patient_id=patient_id,
            plan_date=payload.plan_date,
            data=data,
        )

    # --- Верификация ---

    @classmethod
    async def save_verification(
        cls,
        session: AsyncSession,
        *,
        patient_id: int,
        payload: DailyVerificationCreate,
        submitted_at: Optional[dt.datetime] = None,
    ) -> DailyVerification:
        submitted_at = submitted_at or dt.datetime.now(dt.timezone.utc)

        # Пытаемся найти план на дату верификации
        plan = await crud.get_plan_by_date(
            session,
            patient_id=patient_id,
            plan_date=payload.verification_date,
        )
        retrospective_days = compute_retrospective_days(submitted_at, payload.verification_date)

        data = {
            "plan_id": plan.id if plan else None,
            "submitted_at": submitted_at,
            "dialysis_day": payload.dialysis_day,
            "template_executed": cls._dump_execution(payload.template_executed),
            "pool_added_executed": cls._dump_execution(payload.pool_added_executed),
            "custom_executed": cls._dump_execution(payload.custom_executed),
            "unplanned_executed": payload.unplanned_executed,
            "custom_unplanned": payload.custom_unplanned,
            "day_control_score": payload.day_control_score,
            "retrospective_days": retrospective_days,
        }
        ver = await crud.upsert_verification(
            session,
            patient_id=patient_id,
            verification_date=payload.verification_date,
            data=data,
        )
        return ver

    # --- Метрики ---

    @classmethod
    def compute_metrics_for_day(
        cls,
        *,
        baseline_planning_time: Optional[str],
        plan_date: dt.date,
        dialysis_day: Optional[bool],
        plan: Optional[DailyPlan],
        verification: Optional[DailyVerification],
    ) -> DailyRoutineMetrics:
        """Рассчитать дневные метрики по плану и верификации."""
        baseline_execution_rate: Optional[float] = None
        initiative_rate: Optional[float] = None
        day_control_score: Optional[int] = None
        unplanned_count: Optional[int] = None
        time_allocation_accuracy: Optional[float] = None

        if plan is not None and verification is not None:
            baseline_execution_rate = cls._compute_baseline_execution_rate(plan, verification)
            initiative_rate = cls._compute_initiative_rate(plan, verification)
            time_allocation_accuracy = cls._compute_time_allocation_accuracy(plan, verification)

        if verification is not None:
            day_control_score = verification.day_control_score
            unplanned_count = cls._compute_unplanned_count(verification)

        return DailyRoutineMetrics(
            plan_date=plan_date,
            dialysis_day=dialysis_day,
            planning_time=baseline_planning_time,
            baseline_execution_rate=baseline_execution_rate,
            initiative_rate=initiative_rate,
            day_control_score=day_control_score,
            unplanned_count=unplanned_count,
            time_allocation_accuracy=time_allocation_accuracy,
        )

    # --- Вспомогательные методы сериализации ---

    @staticmethod
    def _dump_activities(
        value: Optional[Dict[ActivityCategory, ActivityPlan]],
    ) -> Optional[dict]:
        if value is None:
            return None
        return {k: v.model_dump() for k, v in value.items()}

    @staticmethod
    def _dump_custom_activities(
        value,
    ):
        if value is None:
            return None
        # Сериализуем список CustomPlannedActivity | None
        result = []
        for item in value:
            if item is None:
                result.append(None)
            else:
                result.append(item.model_dump())
        return result

    @staticmethod
    def _dump_execution(value: Optional[Mapping]) -> Optional[dict]:
        if value is None:
            return None
        dumped: dict = {}
        for key, exec_val in value.items():
            if isinstance(exec_val, ActivityExecution):
                dumped[key] = exec_val.model_dump()
            elif isinstance(exec_val, Mapping):
                dumped[key] = dict(exec_val)
        return dumped

    # --- Метрики (private) ---

    @classmethod
    def _compute_baseline_execution_rate(
        cls,
        plan: DailyPlan,
        verification: DailyVerification,
    ) -> Optional[float]:
        """Выполненные из template_activities / всего template_activities × 100.

        Для диеты используется шкала fully=1.0, partly=0.5, no=0.0.
        Если template_activities пустой — вернуть None.
        """
        tmpl = (plan.template_activities or {}) if isinstance(plan.template_activities, dict) else {}
        executed = (
            verification.template_executed or {}
            if isinstance(verification.template_executed, dict)
            else {}
        )
        if not tmpl:
            return None

        total = 0.0
        achieved = 0.0
        for cat in tmpl.keys():
            total += 1.0
            exec_info = executed.get(cat)
            if not isinstance(exec_info, dict):
                continue
            done = exec_info.get("done")
            if cat == "diet":
                if done == "fully":
                    achieved += 1.0
                elif done == "partly":
                    achieved += 0.5
            else:
                if done == "yes":
                    achieved += 1.0
        if total == 0:
            return None
        return round(achieved / total * 100.0, 2)

    @classmethod
    def _compute_initiative_rate(
        cls,
        plan: DailyPlan,
        verification: DailyVerification,
    ) -> Optional[float]:
        """(выполненные pool_added + выполненные custom) / (добавленные из пула + кастомные) × 100.

        Если ничего не добавлено сверх шаблона — вернуть None.
        """
        added = (
            plan.added_from_pool or {}
            if isinstance(plan.added_from_pool, dict)
            else {}
        )
        custom_planned = plan.custom_activities or []

        executed_pool = (
            verification.pool_added_executed or {}
            if isinstance(verification.pool_added_executed, dict)
            else {}
        )
        executed_custom = (
            verification.custom_executed or {}
            if isinstance(verification.custom_executed, dict)
            else {}
        )

        # Знаменатель: все активности, которые были запланированы сверх шаблона
        denominator = 0
        for cat, info in added.items():
            if isinstance(info, dict) and info.get("planned"):
                denominator += 1
        for item in custom_planned:
            if isinstance(item, dict) and item.get("text"):
                denominator += 1

        if denominator == 0:
            return None

        # Числитель: выполненные из добавленных и кастомных
        numerator = 0
        for cat, info in executed_pool.items():
            if isinstance(info, dict) and info.get("done") == "yes":
                numerator += 1
        for text, info in executed_custom.items():
            if isinstance(info, dict) and info.get("done") == "yes":
                numerator += 1

        return round(numerator / denominator * 100.0, 2)

    @classmethod
    def _compute_unplanned_count(cls, verification: DailyVerification) -> Optional[int]:
        """Кол-во unplanned_executed + выполненных custom_unplanned."""
        count = 0
        if isinstance(verification.unplanned_executed, list):
            count += len(verification.unplanned_executed)
        if verification.custom_unplanned:
            count += 1
        return count

    @classmethod
    def _compute_time_allocation_accuracy(
        cls,
        plan: DailyPlan,
        verification: DailyVerification,
    ) -> Optional[float]:
        """Accuracy распределения времени для избранных категорий.

        Для каждой активности с planned_duration != null и actual_duration != null:
        совпадение = (planned_duration == actual_duration) ? 1 : 0
        accuracy = сумма совпадений / кол-во пар × 100

        Учитываются только категории:
        physical | household | work | leisure | social | self_care
        """
        ALLOWED_CATEGORIES = {
            "physical",
            "household",
            "work",
            "leisure",
            "social",
            "self_care",
        }

        def iter_pairs(
            planned_block: Optional[dict],
            executed_block: Optional[dict],
        ):
            if not isinstance(planned_block, dict) or not isinstance(executed_block, dict):
                return
            for cat, plan_info in planned_block.items():
                if cat not in ALLOWED_CATEGORIES:
                    continue
                if not isinstance(plan_info, dict):
                    continue
                exec_info = executed_block.get(cat)
                if not isinstance(exec_info, dict):
                    continue
                pdur = plan_info.get("planned_duration")
                adur = exec_info.get("actual_duration")
                if pdur is None or adur is None:
                    continue
                yield pdur, adur

        matches = 0
        total = 0

        for pdur, adur in iter_pairs(plan.template_activities or {}, verification.template_executed or {}):
            total += 1
            if pdur == adur:
                matches += 1

        for pdur, adur in iter_pairs(plan.added_from_pool or {}, verification.pool_added_executed or {}):
            total += 1
            if pdur == adur:
                matches += 1

        if total == 0:
            return None
        return round(matches / total * 100.0, 2)


