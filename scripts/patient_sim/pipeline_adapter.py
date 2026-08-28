"""Точка входа в реального ассистента — зеркалит ``researchers/router.py``'s
``/chat-debug/message``: ``classify_request_async`` → ``LLMPipeline.process()``.

Отличие от продовой ручки: ``db=None``. Все стадии пайплайна уже умеют
работать без сессии БД (см. комментарии в ``memory_write.py`` и
``supervisor.py`` — персистентная память и agent tools тихо отключаются,
остальное работает как обычно), поэтому прогон полностью изолирован — ни
одной живой записи в реальные таблицы, не нужен ни существующий patient_id,
ни поднятый Postgres. ``supervisor_state`` между ходами одного сценария
харнесс хранит сам, в памяти процесса, ровно как ``ChatSupervisorState`` в БД
хранил бы его между ходами одного треда в проде.

Один нюанс, обнаруженный живым прогоном: ``db=None`` изолирует пайплайн, но
не сырую телеметрию GigaChat-вызовов — ``app/llm/pool.py`` фонового пишет
каждый вызов в ``llm.llm_call_log`` через свой собственный
``async_session_factory()`` (``app/llm/telemetry.py``), независимо от
``request.db``. У этой таблицы есть FK на ``users.users``, поэтому
``patient_id`` обязан существовать в БД — несуществующий id не роняет прогон
(``telemetry.log_call`` сама глотает ошибку), но каждая попытка на это тратит
round-trip к Postgres и сыплет warning в лог. Поэтому харнесс шлёт все
сценарии от лица одного и того же выделенного тестового пациента (по
умолчанию id=6, «Тест Тестович Тестов» — тот же, которым уже пользуется
ручное тестирование LLM-пайплайна, см. память проекта); разные персоны и
сценарии остаются различимы по ``thread_id``/
``session_key`` в самой телеметрии. Персонажу это не мешает: пол, характер и
история берутся не из его карточки в БД, а передаются харнессом напрямую.

Единственное, что при этом не тестируется: agent tools (RAG-инструменты) и
персистентная семантическая память между ночами — оба требуют
``request.db``. Это осознанный компромисс ради нулевых побочных эффектов на
``chat_messages``/``chat_supervisor_states``/``patient_facts``/витальные
таблицы; см. подвал отчёта.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from app.llm.pipeline import LLMPipeline
from app.llm.pipeline.types import LLMRequest, LLMResponse
from app.llm.router_cascade import classify_request_async

_pipeline = LLMPipeline()

# Выделенный тестовый пациент, которым уже пользуется ручное тестирование
# LLM-пайплайна — нужен только для FK телеметрии
# GigaChat-вызовов (llm.llm_call_log), не для чтения его карточки. Переопределяется
# через PATIENT_SIM_PATIENT_ID, если Dmitry заведёт отдельного sim-пациента.
DEFAULT_PATIENT_ID = int(os.getenv("PATIENT_SIM_PATIENT_ID", "6"))


@dataclass
class TurnResult:
    user_input: str
    response: LLMResponse


class PatientSession:
    """Одна сквозная беседа: несёт supervisor_state между ходами в памяти."""

    def __init__(self, *, patient_gender: str | None, thread_id: str, patient_id: int = DEFAULT_PATIENT_ID):
        self.patient_id = patient_id
        self.patient_gender = patient_gender
        self.thread_id = thread_id
        self._supervisor_state: dict[str, Any] | None = None

    async def send(self, user_input: str) -> TurnResult:
        router_result = await classify_request_async(user_input, "text")
        response = await _pipeline.process(
            LLMRequest(
                patient_id=self.patient_id,
                user_input=user_input,
                source="text",
                router_result=router_result,
                supervisor_state=self._supervisor_state,
                db=None,
                patient_gender=self.patient_gender,
                thread_id=self.thread_id,
            )
        )
        self._supervisor_state = response.supervisor_state
        return TurnResult(user_input=user_input, response=response)
