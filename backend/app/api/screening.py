"""CV screening API (F1, F2): start a "Screen CVs" run for a job and read
the latest results. Interviewers only (N9): candidates never see scores,
rankings or exclusions.

The run works in the background (LangGraph 2, app/graphs/cv_screening.py);
the screen polls the latest run for progress ("12 of 20 CVs").
"""

import logging
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_interviewer
from app.db.database import get_db
from app.db.models import (
    Candidate,
    CandidateScore,
    InterviewSession,
    Job,
    ScreeningRun,
)
from app.db.models.candidate import CandidateStatus
from app.db.models.interview import InvitationStatus, SessionStatus
from app.db.models.run import RunStatus
from app.graphs import cv_screening
from app.runs.runner import start_run
from app.screening.weights import DIMENSIONS, effective_weights

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/jobs",
    tags=["cv screening"],
    dependencies=[Depends(require_interviewer)],
)

NOT_FOUND = "This job no longer exists."
NO_PROFILE = "Save the job profile in the Hiring Assistant chat first."
NO_CVS = "There are no CVs to screen yet."
ALREADY_RUNNING = "Screening is already running for this job."
ACTIVE = (RunStatus.PENDING, RunStatus.RUNNING)


class ScreeningRunOut(BaseModel):
    """One run's status and the weights it used."""

    id: int
    status: RunStatus
    processed: int
    total: int | None
    error: str | None
    weights: dict[str, Any]
    started_at: datetime | None
    finished_at: datetime | None


class ScreenedCandidate(BaseModel):
    """One CV's result in a run."""

    candidate_id: int
    name: str | None
    email: str | None
    cv_filename: str
    outcome: str  # ranked / excluded / unreadable
    rank: int | None
    overall: float | None
    dimensions: dict[str, Any]  # score, weight and reason per dimension
    matches: list[dict[str, Any]]  # per requirement: status and evidence
    summary: str | None
    scanned: bool  # read with OCR
    years_unknown: bool  # years of experience could not be read: check the CV
    # Where the candidate is now: new, shortlisted, invitation_pending,
    # invited, invitation_failed, in_interview, interviewed or selected; and their
    # interview time, if any.
    pipeline: str
    interview_at: datetime | None


class ScreeningOut(BaseModel):
    """The latest run and its results, split into the three lists the
    screen shows; plus what changed since the run."""

    run: ScreeningRunOut | None
    ranked: list[ScreenedCandidate]
    excluded: list[ScreenedCandidate]
    unreadable: list[ScreenedCandidate]
    weights_changed: bool  # the job's weights differ from the run's
    new_cvs: int  # CVs received after the run started


@router.post("/{job_id}/screenings", response_model=ScreeningOut)
def start_screening(
    job_id: int, db: Annotated[Session, Depends(get_db)]
) -> ScreeningOut:
    """Start screening all of the job's CVs (one batch) in the background."""
    job = _job(db, job_id)
    if not (job.profile or {}).get("requirements"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_PROFILE)
    if not _usable_cv_count(db, job_id):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, NO_CVS)
    if _latest_run(db, job_id, active_only=True):
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_RUNNING)
    run = ScreeningRun(job_id=job_id, weights=effective_weights(job))
    db.add(run)
    db.commit()
    start_run(cv_screening.RUN_KIND, run.id)
    logger.info("Screening started: job %d, run %d", job_id, run.id)
    return latest_screening(job_id, db)


@router.get("/{job_id}/screenings/latest", response_model=ScreeningOut)
def latest_screening(
    job_id: int, db: Annotated[Session, Depends(get_db)]
) -> ScreeningOut:
    """The latest run for the job: progress while running, results after."""
    job = _job(db, job_id)
    run = _latest_run(db, job_id)
    if run is None:
        return ScreeningOut(
            run=None,
            ranked=[],
            excluded=[],
            unreadable=[],
            weights_changed=False,
            new_cvs=0,
        )
    rows = db.execute(
        select(CandidateScore, Candidate)
        .join(Candidate, Candidate.id == CandidateScore.candidate_id)
        .where(CandidateScore.screening_run_id == run.id)
    ).all()
    # Each candidate's newest interview that was not cancelled (a cancelled
    # one does not count: they are back on the shortlist).
    sessions = {
        s.candidate_id: s
        for s in db.scalars(
            select(InterviewSession)
            .where(
                InterviewSession.job_id == job_id,
                InterviewSession.status != SessionStatus.CANCELLED,
            )
            .order_by(InterviewSession.id)
        )
    }
    results = [
        _result(score, candidate, sessions.get(candidate.id))
        for score, candidate in rows
    ]
    current = effective_weights(job)
    new_cvs = db.scalar(
        select(func.count(Candidate.id)).where(
            Candidate.job_id == job_id,
            Candidate.status != CandidateStatus.REJECTED,
            Candidate.created_at > run.created_at,
        )
    )
    return ScreeningOut(
        run=ScreeningRunOut.model_validate(run, from_attributes=True),
        ranked=sorted(
            (r for r in results if r.outcome == "ranked"), key=lambda r: r.rank
        ),
        excluded=[r for r in results if r.outcome == "excluded"],
        unreadable=[r for r in results if r.outcome == "unreadable"],
        weights_changed=any(current[d] != run.weights.get(d) for d in DIMENSIONS),
        new_cvs=new_cvs,
    )


def _result(
    score: CandidateScore, candidate: Candidate, session: InterviewSession | None
) -> ScreenedCandidate:
    """One saved result as the screen shows it, with its interview (if any)."""
    if score.passed_gate:
        outcome = "ranked"
    elif (
        candidate.status == CandidateStatus.PARSE_FAILED
        and not score.requirement_matches
    ):
        outcome = "unreadable"
    else:
        outcome = "excluded"
    return ScreenedCandidate(
        candidate_id=candidate.id,
        name=candidate.full_name,
        email=candidate.email,
        cv_filename=candidate.cv_filename,
        outcome=outcome,
        rank=score.rank,
        overall=score.overall_score,
        dimensions=score.dimension_scores or {},
        matches=score.requirement_matches or [],
        summary=score.summary,
        scanned=bool((candidate.parsed_cv or {}).get("used_ocr")),
        years_unknown=(candidate.parsed_cv or {}).get("years_source") == "unknown",
        pipeline=_pipeline(candidate, session),
        interview_at=session.scheduled_at if session else None,
    )


def _pipeline(candidate: Candidate, session: InterviewSession | None) -> str:
    """The candidate's step after screening (design: candidate pipeline)."""
    if candidate.selected_at:
        return "selected"  # the selection email was sent (§4B-14)
    if session is not None and session.status == SessionStatus.LIVE:
        return "in_interview"
    if session is not None and session.status == SessionStatus.ENDED:
        return "interviewed"
    if session is not None:
        return {
            InvitationStatus.PENDING: "invitation_pending",  # not emailed yet
            InvitationStatus.SENT: "invited",
            InvitationStatus.FAILED: "invitation_failed",
        }[session.invitation_status]
    return "shortlisted" if candidate.shortlisted_at else "new"


def _job(db: Session, job_id: int) -> Job:
    """The job, or 404."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return job


def _usable_cv_count(db: Session, job_id: int) -> int:
    """CVs that can be screened (rejected files are not)."""
    return db.scalar(
        select(func.count(Candidate.id)).where(
            Candidate.job_id == job_id, Candidate.status != CandidateStatus.REJECTED
        )
    )


def _latest_run(
    db: Session, job_id: int, active_only: bool = False
) -> ScreeningRun | None:
    """The job's newest screening run (only a pending/running one if asked)."""
    query = select(ScreeningRun).where(ScreeningRun.job_id == job_id)
    if active_only:
        query = query.where(ScreeningRun.status.in_(ACTIVE))
    return db.scalar(query.order_by(ScreeningRun.id.desc()).limit(1))
