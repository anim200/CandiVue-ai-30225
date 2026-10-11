import os

import pytest

# Settings require DATABASE_URL. Unit tests never connect, so a dummy value is
# enough. Inside Docker ("docker compose run --rm tests") the real URL is set.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-that-is-long-enough-0123456789")

from fastapi.testclient import TestClient
from helpers import ScriptedModel
from sqlalchemy import select

from app.ai import llm
from app.auth.security import Role, create_access_token, hash_password
from app.db.database import SessionLocal, check_database
from app.db.models import Job, User
from app.graphs import hiring_assistant
from app.graphs.checkpointer import open_checkpointer
from app.main import app


@pytest.fixture(autouse=True)
def no_real_usage_counting(monkeypatch):
    """Tests never count AI requests in the real usage table; they use the
    default model unless a test chooses otherwise (see test_ai_models.py)."""
    monkeypatch.setattr(llm, "record_request", lambda name: None)
    monkeypatch.setattr(llm, "record_rate_limit", lambda name, error: 99999)
    monkeypatch.setattr(llm, "current_model", lambda: "test-model")


@pytest.fixture(scope="session")
def database_available() -> None:
    """Skip a test when there is no database (e.g. plain local pytest)."""
    if not check_database():
        pytest.skip("needs the database: run 'docker compose run --rm tests'")


@pytest.fixture
def scripted(monkeypatch):
    """Install a scripted LLM; tests fill its list of replies."""
    model = ScriptedModel(replies=[])
    monkeypatch.setattr(llm, "get_chat_model", lambda name: model)
    monkeypatch.setattr(llm, "WAIT_BETWEEN_RETRIES", False)
    return model.replies


@pytest.fixture
def client():
    """App client with the real checkpointer (normally opened at startup)."""
    with open_checkpointer() as checkpointer:
        app.state.checkpointer = checkpointer
        yield TestClient(app)


@pytest.fixture
def headers():
    """A test interviewer's Authorization header; their jobs are removed afterwards."""
    with SessionLocal() as db:
        user = User(
            email="ha.tester@example.com",
            full_name="HA Tester",
            password_hash=hash_password("x" * 10),
        )
        db.add(user)
        db.commit()
        user_id = user.id
    yield {"Authorization": f"Bearer {create_access_token(user_id, Role.INTERVIEWER)}"}
    with open_checkpointer() as checkpointer, SessionLocal() as db:
        for job in db.scalars(select(Job).where(Job.created_by_id == user_id)):
            checkpointer.delete_thread(f"{hiring_assistant.THREAD_KIND}-{job.id}")
            db.delete(job)
        db.delete(db.get(User, user_id))
        db.commit()
