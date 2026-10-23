"""Talent rediscovery API (F11, innovation feature): past applicants of other
jobs who agreed to be considered for other vacancies and fit this job.
Interviewers only (N9).

The check runs after the job's screening and on "Check again"; a match is
only a suggestion: "Add to this job" makes it an applicant (the CV is
copied), and the job's normal steps follow. A candidate's talent-pool
choice can be changed here too (e.g. they asked to be removed).
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.jobs import CvOut, cv_out
from app.auth.dependencies import require_interviewer
from app.db.database import get_db
from app.db.models import (
    Candidate,
    CandidateScore,
    InterviewSession,
    Job,
    RediscoveryMatch,
)
from app.db.models.interview import SessionStatus
from app.db.models.run import RunStatus
from app.graphs import (
    talent_rediscovery,  # noqa: F401 - registers its background run kind
)
from app.interviews import ranking
from app.rediscovery import pool

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/jobs",
    tags=["talent rediscovery"],
    dependencies=[Depends(require_interviewer)],
)

JOB_NOT_FOUND = "This job no longer exists."
NO_PROFILE = "Save the job profile in the Hiring Assistant chat first."
RUNNING = "The talent pool is already being checked for this job."
NOT_A_MATCH = "This person is not among the job's suggestions."
APPLICANT_NOT_FOUND = "This applicant no longer exists."


class RediscoveryRunOut(BaseModel):
    """The latest check: status and progress ("8 of 14 checked")."""

    status: RunStatus
    processed: int
    total: int | None
    error: str | None
    finished_at: datetime | None


class MatchOut(BaseModel):
    """A past applicant who fits this job, with the screening evidence."""

    candidate_id: int  # the original application (in the other job)
    name: str
    email: str | None
    cv_filename: str
    applied_for: str  # the job they applied for
    applied_job_id: int
    applied_at: datetime
    outcome_there: str  # e.g. "Ranked 3 of 12", "Interviewed", "Not ranked: …"
    overall: float
    dimensions: dict[str, Any]
    matches: list[dict[str, Any]]
    added_as: int | None  # their applicant id in this job, once added


class RediscoveryOut(BaseModel):
    """The latest check and its suggestions, best first."""

    run: RediscoveryRunOut | None
    pool_size: int  # past applicants who agreed and could be checked now
    matches: list[MatchOut]


class TalentPoolIn(BaseModel):
    """Whether the applicant is in the talent pool (their own choice)."""

    open_to_other_roles: bool


@router.get("/{job_id}/rediscovery", response_model=RediscoveryOut)
def get_rediscovery(
    job_id: int, db: Annotated[Session, Depends(get_db)]
) -> RediscoveryOut:
    """The latest talent-pool check for the job. Suggestions that no longer
    qualify (e.g. now in another interview, or left the pool) are hidden;
    ones already added stay, marked as added."""
    job = _job(db, job_id)
    run = pool.latest_run(db, job_id)
    eligible = set(pool.pool_ids(db, job))
    added = pool.added_from_pool(db, job_id)
    rows = []
    if run is not None:
        rows = db.execute(
            select(RediscoveryMatch, Candidate, Job)
            .join(Candidate, Candidate.id == RediscoveryMatch.candidate_id)
            .join(Job, Job.id == Candidate.job_id)
            .where(RediscoveryMatch.run_id == run.id)
            .order_by(RediscoveryMatch.overall_score.desc())
        ).all()
    return RediscoveryOut(
        run=RediscoveryRunOut.model_validate(run, from_attributes=True)
        if run
        else None,
        pool_size=len(eligible),
        matches=[
            MatchOut(
                candidate_id=candidate.id,
                name=candidate.full_name or candidate.cv_filename,
                email=candidate.email,
                cv_filename=candidate.cv_filename,
                applied_for=origin_job.title,
                applied_job_id=origin_job.id,
                applied_at=candidate.created_at,
                outcome_there=_outcome(db, origin_job, candidate.id),
                overall=match.overall_score,
                dimensions=match.dimension_scores,
                matches=match.requirement_matches,
                added_as=added.get(candidate.id),
            )
            for match, candidate, origin_job in rows
            if candidate.id in eligible or candidate.id in added
        ],
    )


@router.post("/{job_id}/rediscovery", response_model=RediscoveryOut)
def check_again(job_id: int, db: Annotated[Session, Depends(get_db)]) -> RediscoveryOut:
    """Check the talent pool again (e.g. new applicants agreed since)."""
    job = _job(db, job_id)
    if not (job.profile or {}).get("requirements"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_PROFILE)
    run = pool.latest_run(db, job_id)
    if run is not None and run.status in pool.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, RUNNING)
    pool.start_rediscovery(db, job_id)
    return get_rediscovery(job_id, db)


@router.post("/{job_id}/rediscovery/{candidate_id}/add", response_model=CvOut)
def add_to_job(
    job_id: int, candidate_id: int, db: Annotated[Session, Depends(get_db)]
) -> CvOut:
    """Add a suggested past applicant to this job (copies their CV); screen
    the job again to rank them with the others."""
    job = _job(db, job_id)
    run = pool.latest_run(db, job_id)
    suggested = run is not None and db.scalar(
        select(RediscoveryMatch.id).where(
            RediscoveryMatch.run_id == run.id,
            RediscoveryMatch.candidate_id == candidate_id,
        )
    )
    if not suggested:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_A_MATCH)
    origin = db.get(Candidate, candidate_id)
    try:
        copy = pool.add_to_job(db, job, origin)
    except pool.PoolError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from None
    logger.info("Added from the talent pool: job %d, candidate %d", job_id, copy.id)
    return cv_out(copy, db.get(Job, origin.job_id).title)


@router.put("/{job_id}/cvs/{candidate_id}/talent-pool", response_model=CvOut)
def set_talent_pool(
    job_id: int,
    candidate_id: int,
    body: TalentPoolIn,
    db: Annotated[Session, Depends(get_db)],
) -> CvOut:
    """Record the applicant's talent-pool choice, e.g. when they ask to be
    removed (the form says they can withdraw at any time)."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, APPLICANT_NOT_FOUND)
    candidate.open_to_other_roles = body.open_to_other_roles
    db.commit()
    logger.info(
        "Talent pool %s: candidate %d",
        "joined" if body.open_to_other_roles else "left",
        candidate_id,
    )
    return cv_out(candidate)


def _job(db: Session, job_id: int) -> Job:
    """The job, or 404."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, JOB_NOT_FOUND)
    return job


def _outcome(db: Session, job: Job, candidate_id: int) -> str:
    """How the application did in its own job, in a few words."""
    interviewed = db.scalar(
        select(InterviewSession.id).where(
            InterviewSession.candidate_id == candidate_id,
            InterviewSession.status == SessionStatus.ENDED,
        )
    )
    if interviewed:
        return "Interviewed"
    try:
        run, rows = ranking.latest_rows(db, job)
    except ValueError:
        return "Not screened yet"
    score = db.scalar(
        select(CandidateScore).where(
            CandidateScore.screening_run_id == run.id,
            CandidateScore.candidate_id == candidate_id,
        )
    )
    if score is None:
        return "Not screened yet"
    if score.passed_gate:
        return f"Ranked {score.rank} of {sum(row.ranked for row in rows)}"
    return f"Not ranked: {score.summary}"
