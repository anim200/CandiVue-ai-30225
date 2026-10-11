"""Choosing the AI model and counting its free-tier usage (needs the database).

Uses made-up model names so the real usage numbers are never touched.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.ai import usage
from app.auth.security import Role, create_access_token
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import LlmModel
from app.main import app

pytestmark = pytest.mark.usefixtures("database_available")

MODEL_A, MODEL_B = "test-model-a", "test-model-b"


class GoogleError(Exception):
    """Stands in for Google's error, which carries the JSON answer as .details."""

    def __init__(self, details):
        super().__init__("429")
        self.details = details


def rate_limit_error(details):
    """A rate-limit error caused by Google's answer, as the real client raises it."""
    try:
        raise RuntimeError("rate limited") from GoogleError(details)
    except RuntimeError as error:
        return error


DAILY = {
    "error": {
        "code": 429,
        "details": [
            {
                "violations": [
                    {
                        "quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier",
                        "quotaValue": "20",
                    }
                ]
            },
            {"retryDelay": "48738s"},
        ],
    }
}


@pytest.fixture
def test_models(monkeypatch):
    """Allow two made-up models; remove their rows and restore the choice after."""
    settings = get_settings()
    monkeypatch.setattr(settings, "llm_models", f"{MODEL_A},{MODEL_B}")
    monkeypatch.setattr(settings, "llm_model", MODEL_A)
    with SessionLocal() as db:
        chosen = db.scalar(select(LlmModel.name).where(LlmModel.selected))
    yield
    with SessionLocal() as db:
        db.execute(delete(LlmModel).where(LlmModel.name.in_([MODEL_A, MODEL_B])))
        if chosen:
            db.execute(
                update(LlmModel).where(LlmModel.name == chosen).values(selected=True)
            )
        db.commit()


def row(name):
    """Read a model's usage row."""
    with SessionLocal() as db:
        return db.get(LlmModel, name)


def test_requests_are_counted_per_day(test_models):
    usage.record_request(MODEL_A)
    usage.record_request(MODEL_A)
    assert row(MODEL_A).requests_today == 2

    # A new Google day starts the count again.
    with SessionLocal() as db:
        db.get(LlmModel, MODEL_A).usage_day = usage.google_today() - timedelta(days=1)
        db.commit()
    usage.record_request(MODEL_A)

    assert row(MODEL_A).requests_today == 1


def test_a_daily_limit_is_read_from_googles_answer(test_models):
    wait = usage.record_rate_limit(MODEL_A, rate_limit_error(DAILY))

    saved = row(MODEL_A)
    assert wait == 48738
    assert saved.daily_limit == 20 and saved.requests_today == 20
    assert saved.blocked_until > datetime.now(UTC) + timedelta(hours=13)


def test_an_unknown_rate_limit_waits_a_minute(test_models):
    wait = usage.record_rate_limit(MODEL_A, rate_limit_error(None))

    assert wait == usage.SHORT_WAIT_SECONDS
    assert row(MODEL_A).daily_limit is None


def test_interviewer_can_choose_an_allowed_model(test_models):
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}

    response = client.put("/api/ai/model", headers=headers, json={"name": MODEL_B})

    assert response.status_code == 200
    models = {m["name"]: m for m in response.json()["models"]}
    assert models[MODEL_B]["selected"] and not models[MODEL_A]["selected"]
    assert response.json()["usage_url"].startswith("https://")
    assert usage.current_model() == MODEL_B


def test_a_model_off_the_list_is_refused(test_models):
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}

    response = client.put(
        "/api/ai/model", headers=headers, json={"name": "gpt-unknown"}
    )

    assert response.status_code == 422


def test_candidates_cannot_see_or_change_the_model(test_models):
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {create_access_token(1, Role.CANDIDATE)}"}

    assert client.get("/api/ai/models", headers=headers).status_code == 403
    assert (
        client.put("/api/ai/model", headers=headers, json={"name": MODEL_B}).status_code
        == 403
    )
