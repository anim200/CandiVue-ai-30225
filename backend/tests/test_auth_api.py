"""Sign-in, join by link, "who am I" and the first account (real database).

Synthetic data only. Every test runs inside a transaction that is rolled
back, so nothing is left in the database.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.auth import INTERVIEW_OVER, INVALID_LOGIN, LINK_NOT_RECOGNISED
from app.auth.security import Role, create_access_token, hash_link_token, hash_password
from app.auth.seed import create_first_interviewer
from app.core.config import get_settings
from app.db.database import engine, get_db
from app.db.models import Candidate, InterviewSession, Job, User
from app.db.models.interview import SessionStatus
from app.main import app

pytestmark = pytest.mark.usefixtures("database_available")

EMAIL = "test.interviewer@example.com"
PASSWORD = "test-password-123"
LINK_TOKEN = "test-link-token-0123456789abcdef"


@pytest.fixture
def db():
    """A session whose changes are rolled back after the test."""
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(
            bind=connection, join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        transaction.rollback()


@pytest.fixture
def client(db):
    """The real app, using the rolled-back session for every request."""
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)  # no "with": the startup work is not needed here
    app.dependency_overrides.clear()


@pytest.fixture
def interviewer(db):
    user = User(
        email=EMAIL, full_name="Test Interviewer", password_hash=hash_password(PASSWORD)
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def interview(db):
    job = Job(title="Test Job")
    db.add(job)
    db.flush()
    candidate = Candidate(
        job_id=job.id, full_name="Test Candidate", cv_filename="test.pdf"
    )
    db.add(candidate)
    db.flush()
    session = InterviewSession(
        candidate_id=candidate.id,
        job_id=job.id,
        scheduled_at=datetime(2026, 10, 20, 10, 0, tzinfo=timezone.utc),
        join_token_hash=hash_link_token(LINK_TOKEN),
    )
    db.add(session)
    db.flush()
    return session


def test_interviewer_signs_in(client, interviewer):
    response = client.post(
        "/api/auth/login", json={"email": EMAIL, "password": PASSWORD}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"] == {
        "role": "interviewer",
        "name": "Test Interviewer",
        "email": EMAIL,
        "session_id": None,
    }
    assert body["access_token"]


def test_email_is_not_case_sensitive(client, interviewer):
    response = client.post(
        "/api/auth/login",
        json={"email": "  Test.Interviewer@Example.com ", "password": PASSWORD},
    )

    assert response.status_code == 200


@pytest.mark.parametrize(
    "email, password",
    [(EMAIL, "wrong-password"), ("nobody@example.com", PASSWORD)],
    ids=["wrong password", "unknown email"],
)
def test_failed_sign_in_gives_the_same_message(client, interviewer, email, password):
    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == INVALID_LOGIN


def test_sign_in_input_is_validated(client):
    response = client.post("/api/auth/login", json={"email": "", "password": ""})

    assert response.status_code == 422


def test_me_returns_the_interviewer(client, interviewer):
    token = create_access_token(interviewer.id, Role.INTERVIEWER)

    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

    assert response.json()["email"] == EMAIL


def test_candidate_joins_with_the_link(client, interview):
    response = client.post("/api/auth/candidate", json={"link_token": LINK_TOKEN})

    assert response.status_code == 200
    assert response.json()["user"] == {
        "role": "candidate",
        "name": None,
        "email": None,
        "session_id": interview.id,
    }

    token = response.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.json()["session_id"] == interview.id


def test_unknown_link_is_refused(client, interview):
    response = client.post(
        "/api/auth/candidate", json={"link_token": "not-the-right-token-000000"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == LINK_NOT_RECOGNISED


def test_link_stops_working_after_the_interview(client, db, interview):
    interview.status = SessionStatus.ENDED
    db.flush()

    response = client.post("/api/auth/candidate", json={"link_token": LINK_TOKEN})

    assert response.status_code == 410
    assert response.json()["detail"] == INTERVIEW_OVER


def test_first_interviewer_is_created_from_settings(db, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(
        settings, "demo_interviewer_email", "First.Interviewer@example.com"
    )
    monkeypatch.setattr(settings, "demo_interviewer_password", SecretStr(PASSWORD))
    monkeypatch.setattr(
        db, "commit", db.flush
    )  # keep it inside the rolled-back transaction
    db.execute(delete(User))  # pretend this is a fresh install

    create_first_interviewer(db)

    user = db.scalar(select(User))
    assert user.email == "first.interviewer@example.com"
    assert user.password_hash != PASSWORD


def test_no_second_account_is_created(db, interviewer, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "demo_interviewer_email", "another@example.com")
    monkeypatch.setattr(settings, "demo_interviewer_password", SecretStr(PASSWORD))

    create_first_interviewer(db)

    assert db.scalar(select(User).where(User.email == "another@example.com")) is None
