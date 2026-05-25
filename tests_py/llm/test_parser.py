from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.llm.errors import LLMTransportError
from app.llm.parser import parse_patient_message


pytestmark = [pytest.mark.asyncio, pytest.mark.unit]


async def test_parse_patient_message_returns_empty_dict_on_provider_error(monkeypatch):
    fake_client = SimpleNamespace(call=AsyncMock(side_effect=LLMTransportError("boom")))
    fake_pool = SimpleNamespace(get_available=AsyncMock(return_value=fake_client))

    monkeypatch.setattr("app.llm.pool.pool", fake_pool)

    parsed = await parse_patient_message("пример сообщения", patient_id=7)

    assert parsed == {}
