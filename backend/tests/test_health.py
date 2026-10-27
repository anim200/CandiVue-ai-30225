import pytest
from fastapi.testclient import TestClient

from app.db.database import check_database
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_overrides():
    """Undo any faked dependencies after each test."""
    yield
    app.dependency_overrides.clear()


def test_health_ok_when_database_answers():
    app.dependency_overrides[check_database] = lambda: True

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_degraded_when_database_is_down():
    app.dependency_overrides[check_database] = lambda: False

    response = client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "degraded", "database": "unavailable"}
