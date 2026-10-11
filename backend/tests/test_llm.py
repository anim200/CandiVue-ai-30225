"""AI model access layer: retries, clear failure and the 503 response (N6).

No real AI provider is called: small fake models stand in for it.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.exceptions import ModelRateLimitError
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.ai import llm
from app.ai.llm import AIServiceError, invoke_llm
from app.core.config import get_settings
from app.core.errors import register_error_handlers


@pytest.fixture(autouse=True)
def no_wait_between_retries(monkeypatch):
    """Make retries instant in tests."""
    monkeypatch.setattr(llm, "WAIT_BETWEEN_RETRIES", False)


def use_model(monkeypatch, model):
    """Make invoke_llm() use this fake model."""
    monkeypatch.setattr(llm, "get_chat_model", lambda name: model)


def failing_model(fail_times: int, error=None):
    """A fake model that fails `fail_times` times, then answers."""
    calls = {"count": 0}

    def answer(messages):
        """Fake model: fail the first few calls, then answer "ok"."""
        calls["count"] += 1
        if calls["count"] <= fail_times:
            raise error or TimeoutError("model did not answer in time")
        return AIMessage(content="ok")

    return RunnableLambda(answer), calls


def test_returns_the_model_answer(monkeypatch):
    fake = GenericFakeChatModel(messages=iter([AIMessage(content="Hello")]))
    use_model(monkeypatch, fake)

    assert invoke_llm("Hi").content == "Hello"


def test_prepare_adapts_the_model(monkeypatch):
    model, _calls = failing_model(fail_times=0)
    use_model(monkeypatch, model)
    prepared = []

    invoke_llm("Hi", prepare=lambda m: prepared.append(m) or m)

    assert prepared == [model]


def test_retries_then_succeeds(monkeypatch):
    model, calls = failing_model(fail_times=1)
    use_model(monkeypatch, model)

    assert invoke_llm("Hi").content == "ok"
    assert calls["count"] == 2


def test_gives_up_with_clear_error_after_all_retries(monkeypatch):
    model, calls = failing_model(fail_times=99)
    use_model(monkeypatch, model)

    with pytest.raises(AIServiceError):
        invoke_llm("Hi")
    # One first try plus the configured number of retries.
    assert calls["count"] == get_settings().llm_max_retries + 1


def test_a_daily_limit_is_not_retried(monkeypatch):
    model, calls = failing_model(99, ModelRateLimitError("quota used up"))
    use_model(monkeypatch, model)
    # conftest: the limit lasts a long time (like a daily quota).

    with pytest.raises(AIServiceError, match="test-model has reached its usage limit"):
        invoke_llm("Hi")
    assert calls["count"] == 1  # retrying would only fail again


def test_a_short_rate_limit_is_retried(monkeypatch):
    model, calls = failing_model(1, ModelRateLimitError("too many per minute"))
    use_model(monkeypatch, model)
    monkeypatch.setattr(llm, "record_rate_limit", lambda name, error: 5)

    assert invoke_llm("Hi").content == "ok"
    assert calls["count"] == 2


def test_api_returns_503_when_ai_fails():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/needs-ai")
    def needs_ai():
        """Pretend route whose AI call fails."""
        raise AIServiceError("The AI service is unavailable.")

    response = TestClient(app).get("/needs-ai")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]
