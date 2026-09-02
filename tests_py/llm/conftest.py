import pytest


@pytest.fixture(autouse=True)
def _stub_safety_classifier(monkeypatch, request):
    """2-й эшелон safety (`boundary_guard` → `safety_classifier.classify`, GigaChat-2
    Lite) по умолчанию ON. Юнит-тесты пайплайна не должны из-за этого ходить в сеть
    на первой же стадии — глушим в no-op. Тесты про сам safety-слой отключают эту
    фикстуру маркером `@pytest.mark.real_safety_classifier` или мокают classify сами.
    """
    if request.node.get_closest_marker("real_safety_classifier"):
        return

    from app.llm.safety_classifier import SafetyAssessment

    async def _noop(text, context=None):
        return SafetyAssessment(level="none", subject="self", available=False)

    monkeypatch.setattr("app.llm.pipeline.stages.boundary_guard.safety_classifier.classify", _noop)
