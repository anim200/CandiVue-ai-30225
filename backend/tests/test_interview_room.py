"""The interview room: tickets per role, the waiting room, ending, webhooks,
the chat with the candidate, the CV panel and the assistant in the room.

No LiveKit server is needed: tickets are checked by decoding them with the
test secret, closing a room and pushing chat messages are faked, and
webhooks are signed in the test the same way LiveKit signs them.
"""

import base64
import hashlib
from datetime import timedelta

import jwt
import pytest
from google.protobuf.json_format import MessageToJson
from helpers import call
from langchain_core.messages import AIMessage
from livekit import api
from pydantic import SecretStr

from app.assistant import room_tools
from app.auth.security import Role, create_access_token, hash_password
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Candidate, InterviewSession, Job, User
from app.db.models.interview import InvitationStatus, SessionStatus
from app.interviews import chat, cv_view, planning, room

pytestmark = pytest.mark.usefixtures("database_available")

SECRET = "test-livekit-secret-that-is-long-enough-123"


@pytest.fixture(autouse=True)
def livekit(monkeypatch):
    """A LiveKit secret for the tests; closing a room is only recorded."""
    monkeypatch.setattr(get_settings(), "livekit_api_secret", SecretStr(SECRET))
    closed = []
    monkeypatch.setattr(room, "end_room", closed.append)
    return closed


@pytest.fixture(autouse=True)
def pushed(monkeypatch):
    """Chat messages LiveKit would deliver to the call (only recorded)."""
    sent = []
    monkeypatch.setattr(room, "push_message", lambda sid, msg: sent.append(msg))
    return sent


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
            invitation_status=InvitationStatus.SENT,  # emailed: joining is allowed
        )
        db.add(session)
        db.commit()
        data = {
            "id": session.id,
            "job": job.id,
            "user": user.id,
            "link": token,
            "candidate": candidate.id,
        }
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


def admit(client, data):
    """The interviewer lets the candidate in from the waiting room."""
    return client.post(f"/api/interviews/{data['id']}/admit", headers=interviewer(data))


def test_each_person_gets_a_ticket_for_this_room_only(client, interview):
    room_id = f"interview-{interview['id']}"

    mine = client.post(
        f"/api/interviews/{interview['id']}/room", headers=interviewer(interview)
    ).json()
    admit(client, interview)
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

    assert set(mine) == {
        "job_title",
        "interviewer_name",
        "scheduled_at",
        "duration_minutes",
        "started_at",
        "status",
        "lobby",
    }
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


def test_nobody_joins_before_the_invitation_is_emailed(client, interview):
    with SessionLocal() as db:
        db.get(
            InterviewSession, interview["id"]
        ).invitation_status = InvitationStatus.PENDING
        db.commit()

    mine = client.post(
        f"/api/interviews/{interview['id']}/room", headers=interviewer(interview)
    )
    theirs = client.post("/api/candidate/room", headers=candidate(client, interview))

    assert mine.status_code == 409 and "send it first" in mine.json()["detail"]
    assert theirs.status_code == 409 and "not been sent" in theirs.json()["detail"]


def test_a_helper_that_is_not_a_participant_is_ignored(client, interview):
    body, headers = signed_event("transcriber", f"interview-{interview['id']}")

    answer = client.post("/api/livekit/webhook", content=body, headers=headers)

    assert answer.status_code == 204
    with SessionLocal() as db:
        assert (
            db.get(InterviewSession, interview["id"]).status == SessionStatus.SCHEDULED
        )


# ---------- waiting room ----------


def test_the_candidate_waits_until_let_in(client, interview):
    link = candidate(client, interview)
    boss = interviewer(interview)

    first = client.post("/api/candidate/waiting", headers=link).json()
    refused = client.post("/api/candidate/room", headers=link)
    seen = client.post(
        f"/api/interviews/{interview['id']}/presence", headers=boss
    ).json()
    later = client.post("/api/candidate/waiting", headers=link).json()
    let_in = admit(client, interview).json()
    ticket = client.post("/api/candidate/room", headers=link)
    again = client.post("/api/candidate/room", headers=link)  # a reload or reconnect

    assert first["lobby"] == {"interviewer_present": False, "admitted": False}
    assert refused.status_code == 409 and "let you in" in refused.json()["detail"]
    assert seen["candidate_waiting"] and not seen["admitted"]
    assert later["lobby"] == {"interviewer_present": True, "admitted": False}
    assert let_in["admitted"] and not let_in["candidate_waiting"]
    assert ticket.status_code == 200 and again.status_code == 200


def test_a_closed_page_no_longer_counts_as_there(client, interview):
    client.post("/api/candidate/waiting", headers=candidate(client, interview))
    with SessionLocal() as db:
        db.get(InterviewSession, interview["id"]).candidate_waiting_at = (
            clock.now() - timedelta(seconds=room.PRESENCE_SECONDS + 1)
        )
        db.commit()

    seen = client.post(
        f"/api/interviews/{interview['id']}/presence", headers=interviewer(interview)
    ).json()

    assert not seen["candidate_waiting"]


def test_nobody_is_let_in_after_the_end(client, interview):
    link = candidate(client, interview)
    client.post(
        f"/api/interviews/{interview['id']}/end", headers=interviewer(interview)
    )

    late = admit(client, interview)
    ticket = client.post("/api/candidate/room", headers=link)

    assert late.status_code == 409
    assert ticket.status_code == 410


# ---------- chat ----------


def test_chat_between_interviewer_and_candidate(client, interview, pushed):
    link = candidate(client, interview)
    boss = interviewer(interview)
    url = f"/api/interviews/{interview['id']}/messages"

    early = client.post("/api/candidate/messages", headers=link, json={"text": "Hi?"})
    hello = client.post(url, headers=boss, json={"text": "Welcome! <b>hi</b>"}).json()
    admit(client, interview)
    reply = client.post(
        "/api/candidate/messages", headers=link, json={"text": "Thank you\x07"}
    ).json()
    theirs = client.get("/api/candidate/messages", headers=link).json()
    newer = client.get(f"{url}?after={hello['id']}", headers=boss).json()

    assert early.status_code == 409  # the chat opens once they are let in
    assert hello["sender"] == "interviewer"
    assert hello["text"] == "Welcome! <b>hi</b>"  # kept as plain text, never HTML
    assert reply["text"] == "Thank you"  # the control character was dropped
    assert [m["text"] for m in theirs] == ["Welcome! <b>hi</b>", "Thank you"]
    assert [m["id"] for m in newer] == [reply["id"]]
    assert [m["id"] for m in pushed] == [hello["id"], reply["id"]]


def test_chat_checks_length_speed_and_the_end(client, interview, monkeypatch):
    boss = interviewer(interview)
    url = f"/api/interviews/{interview['id']}/messages"
    monkeypatch.setattr(chat, "RATE_LIMIT", 2)

    too_long = client.post(url, headers=boss, json={"text": "x" * 1001})
    blank = client.post(url, headers=boss, json={"text": "  \n "})
    codes = [
        client.post(url, headers=boss, json={"text": f"m{i}"}).status_code
        for i in range(3)
    ]
    client.post(f"/api/interviews/{interview['id']}/end", headers=boss)
    after_end = client.post(url, headers=boss, json={"text": "late"})

    assert too_long.status_code == 422 and blank.status_code == 422
    assert codes == [200, 200, 422]  # too fast
    assert after_end.status_code == 409
    assert len(client.get(url, headers=boss).json()) == 2  # still readable


def test_the_candidate_never_sees_the_cv_panel_or_the_assistant(client, interview):
    link = candidate(client, interview)
    base = f"/api/interviews/{interview['id']}"

    for path in (
        f"{base}/candidate",
        f"{base}/messages",
        f"/api/assistant/interviews/{interview['id']}/thread",
    ):
        assert client.get(path, headers=link).status_code == 403
    assert client.post(f"{base}/admit", headers=link).status_code == 403
    assert client.post(f"{base}/presence", headers=link).status_code == 403


# ---------- CV panel and the assistant in the room ----------

PARSED = {
    "name": "Alex Strong",
    "email": "alex.strong@example.com",
    "phone": "+880 1700-000099",
    "sections": {
        "skills": (
            "PHP, Laravel, Docker. Contact alex.strong@example.com or "
            "+880 1700-000099, https://github.com/alexstrong (2014 - 2018)"
        )
    },
    "jobs": [{"title": "Senior PHP Developer", "start": "2020-01", "end": "2026-10"}],
    "years_experience": 6.8,
    "years_source": "dates",
    "degree": "bachelor",
    "certifications": ["AWS Certified Developer"],
}


def with_cv(data):
    """Give the interview's candidate a parsed CV (synthetic)."""
    with SessionLocal() as db:
        person = db.get(Candidate, data["candidate"])
        person.parsed_cv = PARSED
        person.email = PARSED["email"]
        db.commit()


def test_cv_panel_and_the_reduced_summary(client, interview):
    with_cv(interview)

    panel = client.get(
        f"/api/interviews/{interview['id']}/candidate", headers=interviewer(interview)
    ).json()
    with SessionLocal() as db:
        summary = cv_view.ai_summary(db, db.get(InterviewSession, interview["id"]))

    assert panel["years"] == 6.8 and panel["degree"] == "bachelor"
    assert panel["email"] == "alex.strong@example.com"  # the interviewer sees it
    assert panel["screening"] is None  # not screened in this test
    assert "Senior PHP Developer" in summary and "Laravel" in summary
    assert "2014 - 2018" in summary  # a date range is not a phone number
    for private in ("Alex", "Strong", "example.com", "1700-000099", "github.com"):
        assert private not in summary  # what goes to the LLM has no contact data


def test_the_room_assistant_has_its_own_thread_and_saves_cv_questions(
    client, interview, scripted, monkeypatch
):
    with_cv(interview)
    boss = interviewer(interview)
    asked = []

    def fake_questions(messages, prepare=None):
        """The structured answer the LLM would give."""
        asked.append(messages)
        return room_tools.CvQuestions(
            questions=[
                room_tools.CvQuestion(
                    question="Tell me about a Laravel API you built.",
                    why="Checks the Laravel claim.",
                    topic="Laravel",
                )
            ]
        )

    monkeypatch.setattr(room_tools, "invoke_llm", fake_questions)
    monkeypatch.setattr(room_tools, "question_bank_size", lambda db: 0)
    scripted += [
        call("questions_from_cv", {}),
        AIMessage(content="Here are questions from the CV."),
        call("questions_from_cv", {}, "c2"),
        AIMessage(content="The same set as before."),
        call("search_question_bank", {"query": "Laravel"}, "c3"),
        AIMessage(content="The question bank is empty. Suggested by the assistant: 1."),
    ]
    url = f"/api/assistant/interviews/{interview['id']}/messages"

    first = client.post(url, headers=boss, json={"text": "Questions from the CV"})
    second = client.post(url, headers=boss, json={"text": "Show them again"}).json()
    third = client.post(url, headers=boss, json={"text": "From the question bank"})
    job_chat = client.get(
        f"/api/assistant/jobs/{interview['job']}/thread", headers=boss
    ).json()

    assert first.status_code == 200 and first.json()["cv_questions_saved"]
    assert len(asked) == 1  # made once per interview: no second AI request
    sent = asked[0][1].content
    assert "Alex" not in sent and "example.com" not in sent
    cards = [item for item in second["items"] if item["kind"] == "questions"]
    assert len(cards) == 2 and cards[1]["saved"] is True
    steps = [i["text"] for i in third.json()["items"] if i["kind"] == "step"]
    assert "The question bank is empty" in steps
    assert job_chat["items"] == []  # the job's own chat is untouched
