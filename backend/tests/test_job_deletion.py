"""Deleting a job with everything about it (needs the database): applicants,
CV files, interviews (scheduled ones cancelled: email and calendar), the
job-board post and the saved workflow state. Synthetic data only."""

from datetime import timedelta

import pytest
from sqlalchemy import select
from test_privacy import save_thread, threads

from app.auth.security import Role, create_access_token
from app.collector import intake
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import (
    Candidate,
    InterviewSession,
    Job,
    QAAnalysis,
    RediscoveryRun,
    ScreeningRun,
)
from app.db.models.interview import InvitationStatus, SessionStatus
from app.db.models.run import RunStatus
from app.integrations.email import EmailError
from app.integrations.job_board import JobBoardError
from app.interviews import emails, room
from app.jobs import deletion

pytestmark = pytest.mark.usefixtures("database_available")

INTERVIEWER = {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}


@pytest.fixture
def outside(monkeypatch, calendar):
    """Fake email, job board and video rooms: what they were asked to do."""
    box = type("Outside", (), {})()
    box.emails, box.deleted_posts, box.closed_rooms = [], [], []
    box.email_fail = box.post_fail = None

    def send(to, subject, text, html=None, invite=None):
        """Record the email, or fail like the email server would."""
        if box.email_fail:
            raise EmailError(box.email_fail)
        box.emails.append({"to": to, "subject": subject, "invite": invite})

    def delete_post(post_id):
        """Record the deleted post, or fail like the job board would."""
        if box.post_fail:
            raise JobBoardError(box.post_fail)
        box.deleted_posts.append(post_id)

    monkeypatch.setattr(emails, "send_email", send)
    monkeypatch.setattr(deletion.job_board, "delete_job_post", delete_post)
    monkeypatch.setattr(room, "end_room", box.closed_rooms.append)
    box.calendar = calendar
    return box


@pytest.fixture
def posted(tmp_path, monkeypatch, calendar):
    """A posted job with three applicants (CV files): one interviewed, one
    with a scheduled interview in the calendar, one not invited; and the
    job's saved assistant chat."""
    monkeypatch.setattr(get_settings(), "cv_intake_dir", str(tmp_path))
    calendar.events["event-1"] = (clock.now(), clock.now())
    with SessionLocal() as db:
        job = Job(
            title="Job deletion test",
            job_board_post_id="999",
            job_board_post_url="https://example.blogspot.com/p/job.html",
        )
        db.add(job)
        db.flush()
        people = []
        for name in ("Pat Ended", "Sam Scheduled", "Lee New"):
            candidate = Candidate(
                job_id=job.id,
                full_name=name,
                email=f"{name.split()[0].lower()}@example.com",
                cv_filename="cv.pdf",
            )
            db.add(candidate)
            db.flush()
            intake.save_cv(job.id, candidate.id, "pdf", b"%PDF-1.4 synthetic")
            people.append(candidate)
        sessions = []
        for candidate, state, when in (
            (people[0], SessionStatus.ENDED, -2),
            (people[1], SessionStatus.SCHEDULED, 48),
        ):
            session = InterviewSession(
                candidate_id=candidate.id,
                job_id=job.id,
                scheduled_at=clock.now() + timedelta(hours=when),
                join_token_hash=f"hash-{candidate.id}",
                invitation_status=InvitationStatus.SENT,
                status=state,
            )
            db.add(session)
            sessions.append(session)
        sessions[1].calendar_event_id = "event-1"
        db.flush()
        db.add(QAAnalysis(session_id=sessions[0].id, status=RunStatus.COMPLETED))
        db.commit()
        ids = {
            "job": job.id,
            "candidates": [c.id for c in people],
            "ended": sessions[0].id,
            "scheduled": sessions[1].id,
        }
    save_thread(f"assistant-job-{ids['job']}")
    yield ids
    with SessionLocal() as db:
        if job := db.get(Job, ids["job"]):
            db.delete(job)
            db.commit()


def test_deleting_a_job_removes_everything_and_cancels_interviews(
    posted, outside, client
):
    answer = client.delete(f"/api/jobs/{posted['job']}", headers=INTERVIEWER)

    assert answer.status_code == 200
    assert answer.json() == {
        "applicants": 3,
        "interviews_cancelled": 1,
        "post_removed": True,
        "problems": [],
    }
    with SessionLocal() as db:
        assert db.get(Job, posted["job"]) is None
        for candidate_id in posted["candidates"]:
            assert db.get(Candidate, candidate_id) is None
        assert db.get(InterviewSession, posted["ended"]) is None
        assert db.get(InterviewSession, posted["scheduled"]) is None
        assert (
            db.scalar(
                select(QAAnalysis.id).where(QAAnalysis.session_id == posted["ended"])
            )
            is None
        )
    assert not intake.cv_folder(posted["job"]).exists()
    assert f"assistant-job-{posted['job']}" not in threads()
    # Only the scheduled interview was cancelled: email, room, calendar.
    (email,) = outside.emails
    assert email["to"] == "sam@example.com" and email["invite"]["method"] == "CANCEL"
    assert outside.closed_rooms == [posted["scheduled"]]
    assert outside.calendar.events == {}
    assert outside.deleted_posts == ["999"]


def test_a_job_board_failure_still_deletes_the_job(posted, outside, client):
    outside.post_fail = "The job board could not be reached."

    answer = client.delete(f"/api/jobs/{posted['job']}", headers=INTERVIEWER)

    assert answer.status_code == 200
    body = answer.json()
    assert body["post_removed"] is False
    (problem,) = body["problems"]
    assert "could not be reached" in problem and "delete it on the blog" in problem
    with SessionLocal() as db:
        assert db.get(Job, posted["job"]) is None


def test_email_and_calendar_failures_are_reported(posted, outside, client):
    outside.email_fail = "The email server refused the message."
    outside.calendar.fail = "The calendar could not be reached."

    answer = client.delete(f"/api/jobs/{posted['job']}", headers=INTERVIEWER)

    assert answer.status_code == 200
    problems = " ".join(answer.json()["problems"])
    assert "Sam Scheduled could not be emailed" in problems
    assert "removed from your calendar" in problems


def test_a_job_never_posted_is_deleted_without_the_job_board(posted, outside, client):
    with SessionLocal() as db:
        db.get(Job, posted["job"]).job_board_post_id = None
        db.commit()

    answer = client.delete(f"/api/jobs/{posted['job']}", headers=INTERVIEWER)

    assert answer.status_code == 200 and answer.json()["post_removed"] is False
    assert outside.deleted_posts == []


@pytest.mark.parametrize(
    "busy, reason",
    [
        ("live", "interview for this job is live"),
        ("screening", "CV screening is still running"),
        ("rediscovery", "talent rediscovery is still running"),
        ("analysis", "interview analysis is still running"),
    ],
)
def test_refused_while_the_job_is_busy(posted, outside, client, busy, reason):
    with SessionLocal() as db:
        if busy == "live":
            db.get(InterviewSession, posted["scheduled"]).status = SessionStatus.LIVE
        elif busy == "screening":
            db.add(ScreeningRun(job_id=posted["job"], status=RunStatus.RUNNING))
        elif busy == "rediscovery":
            db.add(RediscoveryRun(job_id=posted["job"], status=RunStatus.PENDING))
        else:
            analysis = db.scalar(
                select(QAAnalysis).where(QAAnalysis.session_id == posted["ended"])
            )
            analysis.status = RunStatus.RUNNING
        db.commit()

    answer = client.delete(f"/api/jobs/{posted['job']}", headers=INTERVIEWER)

    assert answer.status_code == 409 and reason in answer.json()["detail"]
    with SessionLocal() as db:
        assert db.get(Job, posted["job"]) is not None  # nothing was touched
        assert (
            db.get(InterviewSession, posted["scheduled"]).status
            != SessionStatus.CANCELLED
        )
    assert intake.cv_folder(posted["job"]).exists()
    assert outside.emails == [] and outside.deleted_posts == []


def test_an_unknown_job_is_not_found(outside, client, database_available):
    answer = client.delete("/api/jobs/999999999", headers=INTERVIEWER)

    assert answer.status_code == 404


def test_candidates_cannot_delete_a_job(posted, outside, client):
    token = create_access_token(posted["scheduled"], Role.CANDIDATE)

    answer = client.delete(
        f"/api/jobs/{posted['job']}", headers={"Authorization": f"Bearer {token}"}
    )

    assert answer.status_code == 403
    with SessionLocal() as db:
        assert db.get(Job, posted["job"]) is not None
