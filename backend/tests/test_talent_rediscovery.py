"""Talent rediscovery (F11): the pool rules, a real check through the
screening subgraph (fake embeddings and local model, as in the screening
tests), adding a match to a job, leaving the pool, the consent flag on
uploads and in the form's Sheet, and the route guards."""

from datetime import timedelta

import pytest
from sqlalchemy import select, update
from test_screening_flow import (  # noqa: F401 - fixtures used by name
    PROFILE,
    docx,
    fake_embeddings,
    model_says_no,
)

from app.auth.security import Role, create_access_token
from app.collector import intake
from app.collector.collect import find_columns
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import (
    Candidate,
    CandidateScore,
    CvPassage,
    InterviewSession,
    Job,
    RediscoveryMatch,
    ScreeningRun,
)
from app.db.models.candidate import CandidateStatus
from app.db.models.interview import InvitationStatus, SessionStatus
from app.graphs import cv_screening, talent_rediscovery
from app.interviews import planning
from app.rediscovery import pool
from app.screening.weights import effective_weights

pytestmark = pytest.mark.usefixtures("database_available")

PYTHON_JOB = {
    "title": "Python Backend Developer",
    "min_years_experience": 3,
    "requirements": [
        {"text": "Python", "level": "mandatory", "category": "skill"},
        {"text": "Docker", "level": "mandatory", "category": "skill"},
    ],
}
# Applies for the PHP job, fits the Python job.
CROSSOVER = """Ravi Crossover
ravi.crossover@example.com
Work Experience
Backend Developer · Jan 2017 – Present
Builds Python APIs with Django and PHP sites; every service runs in Docker.
"""
PHP_ONLY = """Lee Plain
lee.plain@example.com
Work Experience
PHP Developer · Jan 2016 – Present
Builds PHP APIs; every service runs in Docker.
"""
NOT_IN_POOL = """Nora Private
nora.private@example.com
Work Experience
Backend Developer · Jan 2017 – Present
Builds Python APIs with Django and PHP sites; every service runs in Docker.
"""


def headers(role=Role.INTERVIEWER):
    """Authorization header for a test user."""
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def add_cv(db, job_id: int, text: str, in_pool: bool) -> int:
    """A candidate with a Word CV for the job."""
    candidate = Candidate(
        job_id=job_id, cv_filename="cv.docx", open_to_other_roles=in_pool
    )
    db.add(candidate)
    db.flush()
    intake.save_cv(job_id, candidate.id, "docx", docx(text))
    return candidate.id


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    """A screened PHP job (three applicants, two in the talent pool) and a
    new Python job without applicants. CV files go to a temporary folder."""
    monkeypatch.setattr(get_settings(), "cv_intake_dir", str(tmp_path))
    with SessionLocal() as db:
        php = Job(title="PHP Developer", profile=PROFILE)
        python = Job(title="Python Backend Developer", profile=PYTHON_JOB)
        db.add_all([php, python])
        db.flush()
        ids = {
            "php": php.id,
            "python": python.id,
            "crossover": add_cv(db, php.id, CROSSOVER, in_pool=True),
            "php_only": add_cv(db, php.id, PHP_ONLY, in_pool=True),
            "private": add_cv(db, php.id, NOT_IN_POOL, in_pool=False),
        }
        run = ScreeningRun(job_id=php.id, weights=effective_weights(php))
        db.add(run)
        db.commit()
        ids["screening"] = run.id
    try:
        cv_screening.run_screening(ids["screening"])  # reads (parses) the CVs
        yield ids
    finally:
        with SessionLocal() as db:
            db.delete(db.get(Job, ids["python"]))
            db.delete(db.get(Job, ids["php"]))
            db.commit()


def ours(ids: list[int], jobs: dict) -> list[int]:
    """Only this test's applicants (the database may hold others)."""
    return [
        i for i in ids if i in (jobs["crossover"], jobs["php_only"], jobs["private"])
    ]


def check(job_id: int) -> int:
    """Run a talent-pool check for the job now; returns the run id."""
    with SessionLocal() as db:
        run_id = pool.start_rediscovery(db, job_id).id
    talent_rediscovery.run_rediscovery(run_id)
    return run_id


# ---------- the pool rules ----------


def test_the_pool_has_only_people_who_agreed_and_are_free(jobs):
    with SessionLocal() as db:
        python = db.get(Job, jobs["python"])
        assert ours(pool.pool_ids(db, python), jobs) == [
            jobs["php_only"],
            jobs["crossover"],
        ]

        # Mid-process in their own job: a scheduled interview, or shortlisted
        # and still waiting for one.
        db.get(Candidate, jobs["php_only"]).shortlisted_at = clock.now()
        db.add(
            InterviewSession(
                candidate_id=jobs["crossover"],
                job_id=jobs["php"],
                scheduled_at=clock.now() + timedelta(days=1),
                join_token_hash=planning.new_link_token()[1],
                invitation_status=InvitationStatus.SENT,
            )
        )
        db.commit()
        assert ours(pool.pool_ids(db, python), jobs) == []

        # After their interview they are free again.
        db.execute(update(InterviewSession).values(status=SessionStatus.ENDED))
        db.get(Candidate, jobs["php_only"]).shortlisted_at = None
        db.commit()
        assert set(ours(pool.pool_ids(db, python), jobs)) == {
            jobs["php_only"],
            jobs["crossover"],
        }


def test_old_applications_and_people_who_already_applied_are_left_out(jobs):
    with SessionLocal() as db:
        python = db.get(Job, jobs["python"])
        db.execute(
            update(Candidate)
            .where(Candidate.id == jobs["php_only"])
            .values(created_at=clock.now() - timedelta(days=400))
        )
        # The same person (same email, other case) applied to the Python job.
        db.add(
            Candidate(
                job_id=python.id,
                cv_filename="own.pdf",
                email="RAVI.CROSSOVER@example.com",
            )
        )
        db.commit()
        assert ours(pool.pool_ids(db, python), jobs) == []


def test_a_person_with_several_applications_is_checked_once(jobs):
    with SessionLocal() as db:
        other = Job(title="Laravel Developer", profile=PROFILE)
        db.add(other)
        db.flush()
        again = Candidate(
            job_id=other.id,
            cv_filename="again.docx",
            email="ravi.crossover@example.com",
            open_to_other_roles=True,
            status=CandidateStatus.PARSED,
        )
        db.add(again)
        db.commit()
        ids = pool.pool_ids(db, db.get(Job, jobs["python"]))
        assert again.id in ids and jobs["crossover"] not in ids  # the latest one
        db.delete(other)
        db.commit()


# ---------- the check ----------


def test_the_check_suggests_past_applicants_who_fit(jobs, background_runs):
    # A finished screening starts the job's check (here: the PHP job's).
    assert (
        pool.RUN_KIND,
        pool.latest_run(SessionLocal(), jobs["php"]).id,
    ) in background_runs

    run_id = check(jobs["python"])

    with SessionLocal() as db:
        found = db.scalars(
            select(RediscoveryMatch).where(RediscoveryMatch.run_id == run_id)
        ).all()
        matches = [m for m in found if ours([m.candidate_id], jobs)]
        run = pool.latest_run(db, jobs["python"])
        assert [m.candidate_id for m in matches] == [jobs["crossover"]]  # has Python
        assert matches[0].overall_score >= pool.SHOW_FROM
        assert any(m["requirement"] == "Python" for m in matches[0].requirement_matches)
        assert run.total >= 2 and run.processed == run.total  # every CV counted
        # Nothing is mixed into the Python job's own screening.
        assert (
            db.scalar(
                select(CandidateScore.id)
                .join(Candidate, Candidate.id == CandidateScore.candidate_id)
                .where(Candidate.job_id == jobs["python"])
            )
            is None
        )


def test_adding_a_match_copies_the_application(jobs, client):
    check(jobs["python"])
    url = f"/api/jobs/{jobs['python']}/rediscovery"

    added = client.post(f"{url}/{jobs['crossover']}/add", headers=headers())

    assert added.status_code == 200
    body = added.json()
    assert (
        body["source"] == "rediscovered"
        and body["rediscovered_from"] == "PHP Developer"
    )
    with SessionLocal() as db:
        copy = db.get(Candidate, body["id"])
        assert copy.job_id == jobs["python"] and copy.status == CandidateStatus.PARSED
        assert intake.find_cv(jobs["python"], copy.id) is not None
        assert db.scalar(select(CvPassage.id).where(CvPassage.candidate_id == copy.id))
        assert (
            db.get(Candidate, jobs["crossover"]).job_id == jobs["php"]
        )  # original stays
    listed = client.get(url, headers=headers()).json()["matches"]
    match = next(m for m in listed if m["candidate_id"] == jobs["crossover"])
    assert match["added_as"] == body["id"] and match["cv_filename"] == "cv.docx"
    again = client.post(f"{url}/{jobs['crossover']}/add", headers=headers())
    assert again.status_code == 409 and "already added" in again.json()["detail"]


def test_leaving_the_pool_hides_the_suggestion(jobs, client):
    check(jobs["python"])
    url = f"/api/jobs/{jobs['php']}/cvs/{jobs['crossover']}/talent-pool"

    left = client.put(url, json={"open_to_other_roles": False}, headers=headers())

    assert left.status_code == 200 and left.json()["open_to_other_roles"] is False
    shown = client.get(
        f"/api/jobs/{jobs['python']}/rediscovery", headers=headers()
    ).json()
    assert jobs["crossover"] not in [m["candidate_id"] for m in shown["matches"]]
    refused = client.post(
        f"/api/jobs/{jobs['python']}/rediscovery/{jobs['crossover']}/add",
        headers=headers(),
    )
    assert refused.status_code == 409


def test_check_again_needs_a_profile_and_one_check_at_a_time(jobs, client):
    with SessionLocal() as db:
        empty = Job(title="No profile yet", profile={})
        db.add(empty)
        db.commit()
        empty_id = empty.id
    assert (
        client.post(f"/api/jobs/{empty_id}/rediscovery", headers=headers()).status_code
        == 422
    )

    first = client.post(f"/api/jobs/{jobs['python']}/rediscovery", headers=headers())
    second = client.post(f"/api/jobs/{jobs['python']}/rediscovery", headers=headers())

    assert first.json()["run"]["status"] == "pending"
    assert second.status_code == 409
    with SessionLocal() as db:
        db.delete(db.get(Job, empty_id))
        db.commit()


# ---------- consent at the door ----------


def test_an_upload_joins_the_pool_only_when_the_interviewer_confirms(jobs, client):
    url = f"/api/jobs/{jobs['python']}/cvs"
    files = {"files": ("a.docx", docx(PHP_ONLY), "application/octet-stream")}

    client.post(url, files=files, headers=headers())
    client.post(
        url, files=files, data={"open_to_other_roles": "true"}, headers=headers()
    )

    flags = [
        c["open_to_other_roles"] for c in client.get(url, headers=headers()).json()
    ]
    assert sorted(flags) == [False, True]


def test_the_form_question_is_read_when_the_form_has_it():
    header = [
        "Timestamp",
        "Full name",
        "Email address",
        "Position applied for",
        "Upload your CV (PDF or Word)",
        "Privacy consent",
        "Talent pool: other vacancies (optional)",
    ]

    assert find_columns(header)["talent_pool"] == 6
    assert "talent_pool" not in find_columns(header[:-1])  # older forms still work


def test_candidates_cannot_see_or_use_the_talent_pool(jobs, client):
    candidate = headers(Role.CANDIDATE)
    base = f"/api/jobs/{jobs['python']}/rediscovery"

    assert client.get(base, headers=candidate).status_code == 403
    assert client.post(base, headers=candidate).status_code == 403
    assert (
        client.post(f"{base}/{jobs['crossover']}/add", headers=candidate).status_code
        == 403
    )
