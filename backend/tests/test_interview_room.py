"""Joining the video call (LiveKit): tickets per role, ending, webhooks.

No LiveKit server is needed: tickets are checked by decoding them with the
test secret, closing a room is faked, and webhooks are signed in the test
the same way LiveKit signs them.
"""

import base64
import hashlib
from datetime import timedelta

import jwt
import pytest
from google.protobuf.json_format import MessageToJson
from livekit import api
from pydantic import SecretStr

from app.auth.security import Role, create_access_token, hash_password
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Candidate, InterviewSession, Job, User
from app.db.models.interview import SessionStatus
from app.interviews import planning, room

pytestmark = pytest.mark.usefixtures("database_available")

SECRET = "test-livekit-secret-that-is-long-enough-123"


@pytest.fixture(autouse=True)
def livekit(monkeypatch):
    """A LiveKit secret for the tests; closing a room is only recorded."""
    monkeypatch.setattr(get_settings(), "livekit_api_secret", SecretStr(SECRET))
    closed = []
    monkeypatch.setattr(room, "end_room", closed.append)
    return closed


@pytest.fixture
def interview():
    """A scheduled interview, its interviewer and the candidate's link."""
    token, token_hash = planning.new_link_token()
    with SessionLocal() as db:
        user = User(
            email="room.tester@example.com",
            full_name="Room Tester",
            password_hash=hash_password("x" * 10),
        )
        job = Job(title="PHP Developer")
        db.add_all([user, job])
        db.flush()
        candidate = Candidate(
            job_id=job.id, full_name="Alex Strong", cv_filename="a.pdf"
        )
        db.add(candidate)
        db.flush()
        session = InterviewSession(
            candidate_id=candidate.id,
            job_id=job.id,
            interviewer_id=None,
            scheduled_at=clock.now() + timedelta(days=3),  # later: join any time
            join_token_hash=token_hash,
        )
        db.add(session)
        db.commit()
        data = {"id": session.id, "job": job.id, "user": user.id, "link": token}
    yield data
    with SessionLocal() as db:
        db.delete(db.get(Job, data["job"]))
        db.delete(db.get(User, data["user"]))
        db.commit()


def interviewer(data):
    """The interviewer's Authorization header."""
    return {
        "Authorization": f"Bearer {create_access_token(data['user'], Role.INTERVIEWER)}"
    }


def candidate(client, data):
    """Sign in with the private link, as the candidate's page does."""
    answer = client.post("/api/auth/candidate", json={"link_token": data["link"]})
    return {"Authorization": f"Bearer {answer.json()['access_token']}"}


def read_ticket(token):
    """The claims of a LiveKit ticket (checks it is signed with our secret)."""
    return jwt.decode(token, SECRET, algorithms=["HS256"])


def test_each_person_gets_a_ticket_for_this_room_only(client, interview):
    room_id = f"interview-{interview['id']}"

    mine = client.post(
        f"/api/interviews/{interview['id']}/room", headers=interviewer(interview)
    ).json()
    theirs = client.post("/api/candidate/room", headers=candidate(client, interview))

    claims = read_ticket(mine["token"])
    assert claims["sub"] == f"interviewer-{interview['user']}"
    assert claims["name"] == "Room Tester"
    assert claims["video"]["roomJoin"] and claims["video"]["room"] == room_id
    assert claims["video"]["canPublishData"] is False  # camera and mic only
    claims = read_ticket(theirs.json()["token"])
    assert claims["sub"] == f"candidate-{interview['id']}"
    assert claims["video"]["room"] == room_id


def test_the_candidate_sees_only_their_interview(client, interview):
    headers = candidate(client, interview)

    mine = client.get("/api/candidate/interview", headers=headers).json()

    assert set(mine) == {"job_title", "scheduled_at", "duration_minutes", "status"}
    assert mine["job_title"] == "PHP Developer"
    assert (
        client.post(
            f"/api/interviews/{interview['id']}/room", headers=headers
        ).status_code
        == 403
    )
    assert (
        client.post("/api/candidate/room", headers=interviewer(interview)).status_code
        == 403
    )


def test_ending_closes_the_call_and_the_link(client, interview, livekit):
    headers = interviewer(interview)
    link = candidate(client, interview)

    ended = client.post(f"/api/interviews/{interview['id']}/end", headers=headers)

    assert ended.status_code == 200 and ended.json()["status"] == "ended"
    assert livekit == [interview["id"]]  # the room was closed
    with SessionLocal() as db:
        assert db.get(InterviewSession, interview["id"]).ended_at is not None
    assert client.post("/api/candidate/room", headers=link).status_code == 410
    again = client.post(f"/api/interviews/{interview['id']}/room", headers=headers)
    assert again.status_code == 409


def test_calls_say_when_they_are_not_set_up(client, interview, monkeypatch):
    monkeypatch.setattr(get_settings(), "livekit_api_secret", None)

    answer = client.post(
        f"/api/interviews/{interview['id']}/room", headers=interviewer(interview)
    )

    assert answer.status_code == 503 and "LIVEKIT_API_SECRET" in answer.json()["detail"]


def signed_event(identity, room_id, secret=SECRET):
    """A participant_joined webhook, signed as LiveKit signs it."""
    event = api.WebhookEvent(
        event="participant_joined",
        room=api.Room(name=room_id),
        participant=api.ParticipantInfo(identity=identity),
    )
    body = MessageToJson(event)
    digest = base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
    token = api.AccessToken("candivue", secret).with_sha256(digest).to_jwt()
    return body, {"Authorization": token, "Content-Type": "application/webhook+json"}


def test_the_first_join_makes_the_interview_live(client, interview):
    body, headers = signed_event(
        f"interviewer-{interview['user']}", f"interview-{interview['id']}"
    )

    answer = client.post("/api/livekit/webhook", content=body, headers=headers)

    assert answer.status_code == 204
    with SessionLocal() as db:
        session = db.get(InterviewSession, interview["id"])
        assert session.status == SessionStatus.LIVE and session.started_at is not None
        assert session.interviewer_id == interview["user"]


def test_a_forged_webhook_is_refused(client, interview):
    body, headers = signed_event(
        "candidate-1", f"interview-{interview['id']}", secret="x" * 43
    )

    answer = client.post("/api/livekit/webhook", content=body, headers=headers)

    assert answer.status_code == 401
    with SessionLocal() as db:
        assert (
            db.get(InterviewSession, interview["id"]).status == SessionStatus.SCHEDULED
        )
