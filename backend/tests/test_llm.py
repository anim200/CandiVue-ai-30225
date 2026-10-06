"""AI model access layer: retries, clear failure and the 503 response (N6).

No real AI provider is called: small fake models stand in for it.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from app.ai import llm
from app.ai.llm import AIServiceError, invoke_llm
from app.core.config import get_settings
from app.core.errors import register_error_handlers


@pytest.fixture(autouse=True)
def no_wait_between_retries(monkeypatch):
    monkeypatch.setattr(llm, "WAIT_BETWEEN_RETRIES", False)


def failing_model(fail_times: int):
    """A fake model that times out `fail_times` times, then answers."""
    calls = {"count": 0}

    def answer(messages):
        calls["count"] += 1
        if calls["count"] <= fail_times:
            raise TimeoutError("model did not answer in time")
        return AIMessage(content="ok")

    return RunnableLambda(answer), calls


def test_returns_the_model_answer():
    model = GenericFakeChatModel(messages=iter([AIMessage(content="Hello")]))

    assert invoke_llm("Hi", model=model).content == "Hello"


def test_retries_then_succeeds():
    model, calls = failing_model(fail_times=1)

    assert invoke_llm("Hi", model=model).content == "ok"
    assert calls["count"] == 2


def test_gives_up_with_clear_error_after_all_retries():
    model, calls = failing_model(fail_times=99)

    with pytest.raises(AIServiceError):
        invoke_llm("Hi", model=model)
    # One first try plus the configured number of retries.
    assert calls["count"] == get_settings().llm_max_retries + 1


def test_api_returns_503_when_ai_fails():
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/needs-ai")
    def needs_ai():
        raise AIServiceError("The AI service is unavailable.")

    response = TestClient(app).get("/needs-ai")

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]
