import os

import pytest

# Settings require DATABASE_URL. Unit tests never connect, so a dummy value is
# enough. Inside Docker ("docker compose run --rm tests") the real URL is set.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-that-is-long-enough-0123456789")

from app.db.database import check_database


@pytest.fixture(scope="session")
def database_available() -> None:
    """Skip a test when there is no database (e.g. plain local pytest)."""
    if not check_database():
        pytest.skip("needs the database: run 'docker compose run --rm tests'")
