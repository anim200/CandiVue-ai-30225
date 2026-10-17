import os

import pytest

# Settings require DATABASE_URL. Unit tests never connect, so a dummy value is
# enough. Inside Docker ("docker compose run --rm tests") the real URL is set.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+psycopg://test:test@localhost:5432/test"
)
os.environ.setdefault("JWT_SECRET", "test-only-secret-that-is-long-enough-0123456789")

import re
import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from helpers import ScriptedModel
from sqlalchemy import select

from app.ai import llm
from app.auth import access_code
from app.auth.security import Role, create_access_token, hash_password
from app.db.database import SessionLocal, check_database
from app.db.models import Job, User
from app.graphs import final_assessment, hiring_assistant, qa_analysis
from app.graphs.checkpointer import open_checkpointer
from app.integrations.calendar import CalendarError
from app.interviews import calendar_sync
from app.main import app
from app.rediscovery import pool


@pytest.fixture(autouse=True)
def access_codes(monkeypatch):
    """No real email in tests: the interview access codes "sent" are kept
    here, newest last ({"to", "code"})."""
    sent = []

    def send(to, subject, text, html=None, invite=None):
        """Remember the code instead of emailing it."""
        code = re.search(r"(\d{3}) (\d{3})", text).group(0).replace(" ", "")
        sent.append({"to": to, "code": code})
        return {"sent_to": to, "message_id": "test"}

    monkeypatch.setattr(access_code, "send_email", send)
    return sent


@pytest.fixture
def candidate_login(client, access_codes):
    """Open an interview link as the candidate's page does (link → emailed
    code → token); returns the verify response."""

    def login(link_token: str):
        """The two steps for one link."""
        sent = client.post("/api/auth/candidate", json={"link_token": link_token})
        if sent.status_code != 200:
            return sent
        code = access_codes[-1]["code"]
        return client.post(
            "/api/auth/candidate/verify", json={"link_token": link_token, "code": code}
        )

    return login


@pytest.fixture(autouse=True)
def no_real_usage_counting(monkeypatch):
    """Tests never count AI requests in the real usage table; they use the
    default model unless a test chooses otherwise (see test_ai_models.py)."""
    monkeypatch.setattr(llm, "record_request", lambda name: None)
    monkeypatch.setattr(llm, "record_rate_limit", lambda name, error: 99999)
    monkeypatch.setattr(llm, "current_model", lambda: "test-model")


@pytest.fixture(autouse=True)
def background_runs(monkeypatch):
    """Ending an interview starts its Q&A analysis (and later its report),
    and a finished screening starts the job's talent-pool check, each in a
    background thread. Tests record the starts instead; the ones that need
    a run call its work function themselves."""
    started = []

    def record(kind, run_id):
        """Remember which run would have started."""
        started.append((kind, run_id))

    monkeypatch.setattr(qa_analysis, "start_run", record)
    monkeypatch.setattr(final_assessment, "start_run", record)
    monkeypatch.setattr(pool, "start_run", record)
    return started


@pytest.fixture(autouse=True)
def calendar(monkeypatch):
    """No real Google Calendar: events are kept in .events {id: (start, end)};
    .busy holds busy periods to report, .fail makes every call fail."""
    box = SimpleNamespace(events={}, busy=[], fail=None)

    def check():
        """Fail like the calendar server would, if asked to."""
        if box.fail:
            raise CalendarError(box.fail)

    def add_event(summary, start, end, description):
        """Keep the event; return a new id."""
        check()
        event_id = uuid.uuid4().hex
        box.events[event_id] = (start, end)
        return event_id

    def move_event(event_id, start, end):
        """Move a kept event."""
        check()
        box.events[event_id] = (start, end)

    def delete_event(event_id):
        """Forget a kept event."""
        check()
        box.events.pop(event_id, None)

    def busy(start, end):
        """The busy periods the test set."""
        check()
        return box.busy

    fake = SimpleNamespace(
        busy=busy, add_event=add_event, move_event=move_event, delete_event=delete_event
    )
    monkeypatch.setattr(calendar_sync, "calendar", fake)
    return box


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
