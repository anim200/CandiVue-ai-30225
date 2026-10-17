"""The talent pool and its rules (F11).

Who is in the pool for a job (pool_ids), all must hold:
- the applicant agreed to be considered for other vacancies (opt-in,
  open_to_other_roles); without it they are never matched;
- the application is for another job, its CV was read (parsed), and it is
  not older than REDISCOVERY_MAX_AGE_DAYS (data minimisation, N16);
- they are not in the middle of their own process: no scheduled or live
  interview, and not shortlisted while still waiting for one;
- they have not applied to this job already (same email address), and
  were not added to it from the pool before.
A person who applied to several jobs is checked once, with their latest
application.

Matching uses the existing screening (no new AI); a match is only a
suggestion: the interviewer decides whether to add the application to the
job (add_to_job), and the normal steps follow (screen, shortlist, invite).
"""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.collector.intake import find_cv, save_cv
from app.core import clock
from app.core.config import get_settings
from app.db.models import Candidate, CvPassage, InterviewSession, Job, RediscoveryRun
from app.db.models.candidate import CandidateStatus
from app.db.models.interview import SessionStatus
from app.db.models.run import RunStatus
from app.runs.runner import start_run

RUN_KIND = "talent_rediscovery"
SHOW_FROM = 50  # lowest overall score shown as a possible fit (0-100)
ACTIVE = (RunStatus.PENDING, RunStatus.RUNNING)


class PoolError(Exception):
    """The application cannot be added (the message is safe to show)."""


def pool_ids(db: Session, job: Job) -> list[int]:
    """The applications (candidate ids) in this job's talent pool, newest
    first (see the module docstring for the rules)."""
    since = clock.now() - timedelta(days=get_settings().rediscovery_max_age_days)
    applied = _applied(db, job.id)
    busy = _mid_process(db)
    seen, ids = set(), []
    for candidate in db.scalars(
        select(Candidate)
        .where(
            Candidate.open_to_other_roles.is_(True),
            Candidate.job_id != job.id,
            Candidate.status == CandidateStatus.PARSED,
            Candidate.created_at >= since,
        )
        .order_by(Candidate.created_at.desc(), Candidate.id.desc())
    ):
        person = _person(candidate)
        if candidate.id in busy or person in applied["people"] or person in seen:
            continue
        if candidate.id in applied["origins"]:
            continue
        seen.add(person)
        ids.append(candidate.id)
    return ids


def latest_run(db: Session, job_id: int) -> RediscoveryRun | None:
    """The job's latest talent-pool check, if any."""
    return db.scalar(
        select(RediscoveryRun)
        .where(RediscoveryRun.job_id == job_id)
        .order_by(RediscoveryRun.id.desc())
        .limit(1)
    )


def start_rediscovery(db: Session, job_id: int) -> RediscoveryRun:
    """Check the talent pool for a job in the background (or return the
    check that is already running)."""
    run = latest_run(db, job_id)
    if run is not None and run.status in ACTIVE:
        return run
    run = RediscoveryRun(job_id=job_id)
    db.add(run)
    db.commit()
    start_run(RUN_KIND, run.id)
    return run


def added_from_pool(db: Session, job_id: int) -> dict[int, int]:
    """Applications added to this job from the pool: {original id: new id}."""
    return dict(
        db.execute(
            select(Candidate.rediscovered_from_id, Candidate.id).where(
                Candidate.job_id == job_id, Candidate.rediscovered_from_id.is_not(None)
            )
        ).all()
    )


def add_to_job(db: Session, job: Job, origin: Candidate) -> Candidate:
    """Add a past application to this job as a new applicant: the CV file,
    the parsed CV and its passages are copied (nothing is read again), and
    the new applicant remembers where it came from. The original stays."""
    if origin.id in added_from_pool(db, job.id):
        raise PoolError("This person was already added to this job.")
    if origin.id not in pool_ids(db, job):
        raise PoolError(
            "This person can no longer be added: they may have applied already, "
            "be in another interview, or no longer be in the talent pool."
        )
    source = find_cv(origin.job_id, origin.id)
    if source is None:
        raise PoolError("The CV file of this application is missing.")
    copy = Candidate(
        job_id=job.id,
        full_name=origin.full_name,
        email=origin.email,
        phone=origin.phone,
        cv_filename=origin.cv_filename,
        parsed_cv=origin.parsed_cv,
        status=CandidateStatus.PARSED,
        open_to_other_roles=True,
        rediscovered_from_id=origin.id,
    )
    db.add(copy)
    db.flush()  # the new id names the copied file
    save_cv(job.id, copy.id, source.suffix.lstrip("."), source.read_bytes())
    db.add_all(
        CvPassage(
            candidate_id=copy.id,
            position=passage.position,
            section=passage.section,
            text=passage.text,
            embedding=passage.embedding,
        )
        for passage in db.scalars(
            select(CvPassage).where(CvPassage.candidate_id == origin.id)
        )
    )
    db.commit()
    return copy


def _person(candidate: Candidate) -> str:
    """Who an application belongs to: the email address, or the application
    itself when there is none."""
    return (candidate.email or "").strip().lower() or f"candidate-{candidate.id}"


def _applied(db: Session, job_id: int) -> dict[str, set]:
    """Who already applied to the job, and which pool applications were
    added to it."""
    rows = db.scalars(select(Candidate).where(Candidate.job_id == job_id)).all()
    return {
        "people": {_person(c) for c in rows if c.email},
        "origins": {c.rediscovered_from_id for c in rows if c.rediscovered_from_id},
    }


def _mid_process(db: Session) -> set[int]:
    """Applications still in their own process: a scheduled or live
    interview, or shortlisted and not interviewed yet."""
    sessions = db.execute(
        select(InterviewSession.candidate_id, InterviewSession.status)
    ).all()
    active = {
        cid for cid, s in sessions if s in (SessionStatus.SCHEDULED, SessionStatus.LIVE)
    }
    interviewed = {cid for cid, s in sessions if s == SessionStatus.ENDED}
    shortlisted = set(
        db.scalars(select(Candidate.id).where(Candidate.shortlisted_at.is_not(None)))
    )
    return active | (shortlisted - interviewed)
