import pytest

# Живые ручные прогоны по new_agent_comcept/MANUAL_TEST_PLAN.md держат эти
# флаги в .env между рестартами сервера — включая LLM_SINGLE_AGENT=1, потому
# что фаза 1 плана требует именно этого. load_environment() в
# tests_py/conftest.py читает тот же .env, так что без явного сброса здесь
# юнит-тесты старой ветки (test_supervisor_gate.py, test_pipeline.py и т.п.,
# которые мокают run_first_module и не трогают Agent/pool) начинают тихо
# исполняться по одноагентной ветке и падают — поведение зависит от того,
# что оставил в .env последний ручной прогон, а не от кода теста.
_MANUAL_TEST_PLAN_FLAGS = (
    "LLM_SINGLE_AGENT",
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
