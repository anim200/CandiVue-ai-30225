"""Dashboard (home page): the counts, the next steps, the next interviews
and applications per day, read-only and for interviewers only. The tests
share the database with the app, so counts are compared before and after
adding test data. Synthetic data only."""

from datetime import timedelta

import pytest

from app import dashboard
from app.auth.security import Role, create_access_token
from app.core import clock
from app.db.database import SessionLocal
from app.db.models import (
    AssessmentReport,
    Candidate,
    InterviewSession,
    Job,
    ScreeningRun,
)
from app.db.models.assessment import ReviewStatus
from app.db.models.candidate import CandidateStatus
from app.db.models.interview import InvitationStatus, SessionStatus
from app.db.models.job import JobStatus
from app.db.models.run import RunStatus

pytestmark = pytest.mark.usefixtures("database_available")

INTERVIEWER = {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}
TITLE = "Dashboard Test Job"


def counts() -> dict:
    """The dashboard's counts right now."""
    with SessionLocal() as db:
        return dashboard.summary(db)["counts"]


@pytest.fixture
def job():
    """An open test job with three CVs (one rejected), screened once, a
    live interview, one later today, one tomorrow, an ended interview
    whose report waits for review, and a selected candidate."""
    now = clock.now()
    today = now.astimezone(clock.local_zone()).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    with SessionLocal() as db:
        job = Job(title=TITLE, status=JobStatus.OPEN)
        db.add(job)
        db.flush()
        people = []
        for i, status in enumerate(
            (
                CandidateStatus.PARSED,
                CandidateStatus.PARSED,
                CandidateStatus.REJECTED,
                CandidateStatus.PARSED,
            )
        ):
            person = Candidate(
                job_id=job.id,
                full_name=f"Test Person {i}",
                cv_filename=f"cv{i}.pdf",
                status=status,
            )
            db.add(person)
            people.append(person)
        db.flush()
        run = ScreeningRun(job_id=job.id, weights={}, status=RunStatus.COMPLETED)
        db.add(run)
        db.flush()
        run.created_at = now + timedelta(minutes=1)  # after the CVs: nothing new yet
        people[0].selected_at = now

        def session(person, at, status=SessionStatus.SCHEDULED):
            """An invited interview of one test person."""
            item = InterviewSession(
                candidate_id=person.id,
                job_id=job.id,
                scheduled_at=at,
                join_token_hash=f"dash-{person.id}-{at.timestamp()}",
                invitation_status=InvitationStatus.SENT,
                status=status,
            )
            db.add(item)
            db.flush()
            return item

        live = session(people[0], now - timedelta(minutes=10), SessionStatus.LIVE)
        later = session(
            people[1], max(now + timedelta(minutes=5), today + timedelta(hours=23))
        )
        tomorrow = session(people[3], today + timedelta(days=1, hours=10))
        ended = session(people[1], now - timedelta(days=1), SessionStatus.ENDED)
        db.add(
            AssessmentReport(
                candidate_id=people[1].id,
                session_id=ended.id,
                status=RunStatus.WAITING_FOR_REVIEW,
                review_status=ReviewStatus.PENDING_REVIEW,
                content={"version": 1},
            )
        )
        db.commit()
        ids = {
            "job": job.id,
            "live": live.id,
            "later": later.id,
            "tomorrow": tomorrow.id,
            "ended": ended.id,
        }
    yield ids
    with SessionLocal() as db:
        if found := db.get(Job, ids["job"]):  # a test may have deleted it
            db.delete(found)
            db.commit()


def test_the_counts_include_the_new_data(client):
    before = counts()
    with SessionLocal() as db:
        fresh = Job(title=TITLE, status=JobStatus.OPEN)
        db.add(fresh)
        db.flush()
        db.add(
            Candidate(job_id=fresh.id, full_name="New Applicant", cv_filename="cv.pdf")
        )
        db.add(
            Candidate(
                job_id=fresh.id, cv_filename="bad.exe", status=CandidateStatus.REJECTED
            )
        )
        db.commit()
        fresh_id = fresh.id
    try:
        after = counts()
        assert after["open_jobs"] == before["open_jobs"] + 1
        assert (
            after["applications_week"] == before["applications_week"] + 1
        )  # not the rejected file
        assert after["cvs_to_screen"] == before["cvs_to_screen"] + 1  # never screened
    finally:
        with SessionLocal() as db:
            db.delete(db.get(Job, fresh_id))
            db.commit()


def test_interviews_reports_and_selections_are_counted(job, client):
    data = client.get("/api/dashboard", headers=INTERVIEWER).json()
    with SessionLocal() as db:
        db.delete(db.get(Job, job["job"]))
        db.commit()
    without = counts()

    assert (
        data["counts"]["interviews_today"] - without["interviews_today"] == 2
    )  # live + later
    assert data["counts"]["reports_to_review"] - without["reports_to_review"] == 1
    assert data["counts"]["selected_month"] - without["selected_month"] == 1


def test_next_steps_put_the_live_interview_first(job, client):
    steps = client.get("/api/dashboard", headers=INTERVIEWER).json()["next_steps"]
    ours = [s for s in steps if s["detail"] == TITLE]

    assert (
        ours[0]["kind"] == "live"
        and ours[0]["link"] == f"/interviews/{job['live']}/room"
    )
    assert ours[0]["action"] == "Rejoin"
    kinds = [s["kind"] for s in ours]
    assert "interview" in kinds and "review" in kinds
    review = next(s for s in ours if s["kind"] == "review")
    assert review["link"] == f"/interviews/{job['ended']}/report"
    assert all(s["kind"] != "screen" for s in ours)  # screened after every CV


def test_new_cvs_and_a_passed_deadline_ask_for_a_screening(job):
    with SessionLocal() as db:
        run = db.query(ScreeningRun).filter_by(job_id=job["job"]).one()
        run.created_at = clock.now()  # screened after the CVs so far
        db.commit()
        db.add(
            Candidate(
                job_id=job["job"], full_name="Late Applicant", cv_filename="late.pdf"
            )
        )
        db.commit()
        step = dashboard._job_step(db, db.get(Job, job["job"]))
        assert step["kind"] == "screen" and step["text"].startswith(
            "1 new CV to screen"
        )

        # Applications closed after that screening (and before now).
        db.get(Job, job["job"]).applications_close_at = clock.now()
        db.commit()
        step = dashboard._job_step(db, db.get(Job, job["job"]))
        assert "have closed: screen again before inviting" in step["text"]


def test_a_running_screening_has_nothing_to_screen(job):
    with SessionLocal() as db:
        run = db.query(ScreeningRun).filter_by(job_id=job["job"]).one()
        run.status = RunStatus.RUNNING
        db.add(Candidate(job_id=job["job"], full_name="Another", cv_filename="x.pdf"))
        db.commit()
        assert dashboard.cvs_to_screen(db, db.get(Job, job["job"])) == 0


def test_upcoming_lists_today_and_later_soonest_first(job, client):
    upcoming = client.get("/api/dashboard", headers=INTERVIEWER).json()["upcoming"]
    ours = [u["id"] for u in upcoming if u["job_title"] == TITLE]

    assert ours[: ours.index(job["tomorrow"]) + 1][-1] == job["tomorrow"]
    assert job["ended"] not in ours  # past interviews are not upcoming
    assert ours.index(job["live"]) < ours.index(job["tomorrow"])


def test_applications_per_day_cover_fourteen_days(job, client):
    days = client.get("/api/dashboard", headers=INTERVIEWER).json()["applications"]
    today = clock.now().astimezone(clock.local_zone()).date().isoformat()

    assert len(days) == dashboard.CHART_DAYS
    assert days[-1]["day"] == today and days[-1]["count"] >= 3  # not the rejected CV
    assert days == sorted(days, key=lambda d: d["day"])


def test_candidates_cannot_see_the_dashboard(job, client):
    token = create_access_token(job["live"], Role.CANDIDATE)

    answer = client.get("/api/dashboard", headers={"Authorization": f"Bearer {token}"})

    assert answer.status_code == 403
