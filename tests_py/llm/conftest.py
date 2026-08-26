import pytest

# Живые ручные прогоны по new_agent_comcept/MANUAL_TEST_PLAN.md держат эти
# флаги в .env между рестартами сервера. load_environment() в
# tests_py/conftest.py читает тот же .env, так что без явного сброса здесь
# юнит-тесты, которые проверяют поведение конкретной фазы каскада (L0/L1/L2,
# инструменты агента), начинают тихо исполняться по той фазе, что оставил в
# .env последний ручной прогон, а не по той, что задаёт тело теста.
_MANUAL_TEST_PLAN_FLAGS = (
    "LLM_ROUTER_L0",
    "LLM_ROUTER_L1",
    "LLM_ROUTER_L2",
    "LLM_AGENT_TOOLS",
)


@pytest.fixture(autouse=True)
def _reset_manual_test_plan_flags(monkeypatch):
    """Тесты стартуют с этими флагами выключенными, независимо от .env.

    Тест, которому нужен конкретный флаг включённым, ставит его явно через
    monkeypatch.setenv в своём теле — это выполняется после этой фикстуры
    и переопределяет сброс, конфликта нет.
    """
    for flag in _MANUAL_TEST_PLAN_FLAGS:
        monkeypatch.delenv(flag, raising=False)
