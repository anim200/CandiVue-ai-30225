import os

import pytest

# Settings require DATABASE_URL. Unit tests never connect, so a dummy value is
# enough. Inside Docker ("docker compose run --rm tests") the real URL is set.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-that-is-long-enough-0123456789")

from app.ai import llm
from app.db.database import check_database


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
