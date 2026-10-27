"""Sign-in, join by link with the emailed code, "who am I" and the first
account (real database).

Synthetic data only. Every test runs inside a transaction that is rolled
back, so nothing is left in the database.
"""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.api.auth import INTERVIEW_OVER, INVALID_LOGIN, LINK_NOT_RECOGNISED
from app.auth.access_code import EXPIRED, NO_EMAIL, TOO_MANY
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
    """Create a test interviewer account (rolled back afterwards)."""
    user = User(
        email=EMAIL, full_name="Test Interviewer", password_hash=hash_password(PASSWORD)
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def interview(db):
    """Create a test job, candidate and interview with a known link token."""
    job = Job(title="Test Job")
    db.add(job)
    db.flush()
    candidate = Candidate(
        job_id=job.id,
        full_name="Test Candidate",
        email="test.candidate@example.com",
        cv_filename="test.pdf",
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


def open_link(client, again=False):
    """Open the interview link: the code is emailed."""
    return client.post(
        "/api/auth/candidate", json={"link_token": LINK_TOKEN, "again": again}
    )


def verify(client, code):
    """Enter the code from the email."""
    return client.post(
        "/api/auth/candidate/verify", json={"link_token": LINK_TOKEN, "code": code}
    )


def wrong(code: str) -> str:
    """A code that is not this one."""
    return "000000" if code != "000000" else "111111"


def test_candidate_joins_with_the_link_and_the_emailed_code(
    client, interview, access_codes
):
    sent = open_link(client)

    assert sent.status_code == 200
    assert sent.json() == {"email_hint": "t•••@example.com", "resend_in": 60}
    assert access_codes[-1]["to"] == "test.candidate@example.com"
    open_link(client)  # opened again a moment later: no second email
    assert len(access_codes) == 1
    code = access_codes[-1]["code"]
    refused = verify(client, wrong(code))
    assert refused.status_code == 400
    assert refused.json()["detail"] == "That code is not right. 4 tries left."

    response = verify(client, code)

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
    assert verify(client, code).json()["detail"] == EXPIRED  # a code works once


def test_a_forwarded_link_without_the_code_gets_nowhere(
    client, interview, access_codes
):
    open_link(client)
    code = access_codes[-1]["code"]

    answers = [verify(client, wrong(code)).json()["detail"] for _ in range(5)]

    assert answers[-1] == TOO_MANY
    assert verify(client, code).json()["detail"] == TOO_MANY  # even the right one now
    assert open_link(client, again=True).json()["resend_in"] > 0  # not at once
    assert len(access_codes) == 1


def test_an_expired_code_is_replaced_by_a_new_one(client, db, interview, access_codes):
    open_link(client)
    first = access_codes[-1]["code"]
    interview.access_code_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    interview.access_code_sent_at = datetime.now(timezone.utc) - timedelta(minutes=11)
    db.flush()

    assert verify(client, first).json()["detail"] == EXPIRED
    assert open_link(client, again=True).json()["resend_in"] == 60
    assert verify(client, access_codes[-1]["code"]).status_code == 200


def test_without_an_email_address_no_code_can_be_sent(client, db, interview):
    db.get(Candidate, interview.candidate_id).email = None
    db.flush()

    answer = open_link(client)

    assert answer.status_code == 503 and answer.json()["detail"] == NO_EMAIL


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
