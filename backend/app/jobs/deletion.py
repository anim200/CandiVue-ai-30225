"""Deleting a job (the interviewer confirms it on the job page).

Everything that belongs to the job goes: its applicants with their CVs,
scores, interviews, transcripts, analyses and reports (the database rows
cascade, N19), the CV files, the saved workflow state and the job-board
post. Scheduled interviews are cancelled first, the normal way: the
candidate gets the cancellation email and the calendar event is removed.

It is refused while one of the job's background runs is still working
(screening, talent rediscovery, Q&A analysis, report) or an interview is
live, because those would write to rows that no longer exist. A job-board
or calendar failure never stops the deletion: the result says what to
remove by hand.
"""

import logging
import shutil
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.collector.intake import cv_folder
from app.db.models import (
    AssessmentReport,
    Candidate,
    InterviewSession,
    Job,
    QAAnalysis,
    RediscoveryRun,
    ScreeningRun,
)
from app.db.models.interview import SessionStatus
from app.db.models.run import RunStatus
from app.integrations import job_board
from app.integrations.job_board import JobBoardError
from app.interviews import calendar_sync, planning, room
from app.runs.cleanup import purge_stale_threads

logger = logging.getLogger(__name__)

ACTIVE = (RunStatus.PENDING, RunStatus.RUNNING)
# The background runs that write to the job's rows while they work.
JOB_RUNS = {"CV screening": ScreeningRun, "talent rediscovery": RediscoveryRun}
INTERVIEW_RUNS = {
    "interview analysis": QAAnalysis,
    "assessment report": AssessmentReport,
}
LIVE = "An interview for this job is live: end it first, then delete the job."
RUNNING = "The {what} is still running: wait until it finishes, then delete the job."
CALENDAR_FAILED = (
    "{name}'s interview could not be removed from your calendar ({reason})."
)
EMAIL_FAILED = "{name} could not be emailed about the cancellation ({reason})."
POST_FAILED = (
    "The job-board post could not be removed ({reason}): delete it on the blog."
)


class JobBusy(Exception):
    """The job cannot be deleted now (the message says why)."""


@dataclass
class Deleted:
    """What deleting the job did."""

    applicants: int
    interviews_cancelled: int
    post_removed: bool  # False also when the job was never posted
    problems: list[str] = field(default_factory=list)  # what to do by hand


def delete_job(db: Session, job: Job) -> Deleted:
    """Delete the job and everything about it; JobBusy if it is not possible
    now."""
    _check_not_busy(db, job.id)
    result = Deleted(
        applicants=db.scalar(
            select(func.count(Candidate.id)).where(Candidate.job_id == job.id)
        ),
        interviews_cancelled=0,
        post_removed=False,
    )
    for session in db.scalars(
        select(InterviewSession).where(
            InterviewSession.job_id == job.id,
            InterviewSession.status == SessionStatus.SCHEDULED,
        )
    ).all():
        result.problems += _cancel(db, session)
        result.interviews_cancelled += 1
    if job.job_board_post_id:
        try:
            job_board.delete_job_post(job.job_board_post_id)
            result.post_removed = True
        except JobBoardError as exc:
            result.problems.append(POST_FAILED.format(reason=str(exc).rstrip(".")))
    job_id = job.id
    db.delete(job)
    db.commit()
    shutil.rmtree(cv_folder(job_id), ignore_errors=True)
    purge_stale_threads(db)
    logger.info(
        "Job deleted: job %d (%d applicants, %d interviews cancelled)",
        job_id,
        result.applicants,
        result.interviews_cancelled,
    )
    return result


def _check_not_busy(db: Session, job_id: int) -> None:
    """JobBusy if a background run of the job is working or an interview is live."""
    if db.scalar(
        select(InterviewSession.id).where(
            InterviewSession.job_id == job_id,
            InterviewSession.status == SessionStatus.LIVE,
        )
    ):
        raise JobBusy(LIVE)
    for what, model in JOB_RUNS.items():
        running = select(model.id).where(
            model.job_id == job_id, model.status.in_(ACTIVE)
        )
        if db.scalar(running.limit(1)):
            raise JobBusy(RUNNING.format(what=what))
    for what, model in INTERVIEW_RUNS.items():
        running = (
            select(model.id)
            .join(InterviewSession, InterviewSession.id == model.session_id)
            .where(InterviewSession.job_id == job_id, model.status.in_(ACTIVE))
        )
        if db.scalar(running.limit(1)):
            raise JobBusy(RUNNING.format(what=what))


def _cancel(db: Session, session: InterviewSession) -> list[str]:
    """Cancel a scheduled interview like the Cancel button does; returns
    what went wrong (email, calendar)."""
    session.status = SessionStatus.CANCELLED
    db.commit()
    room.end_room(session.id)
    email = planning.cancel_notice(db, session)
    calendar = calendar_sync.sync(db, session)
    db.commit()
    name = db.get(Candidate, session.candidate_id).full_name or "A candidate"
    problems = []
    if email not in (None, "sent"):
        problems.append(EMAIL_FAILED.format(name=name, reason=email.rstrip(".")))
    if calendar not in (None, "removed"):
        problems.append(CALENDAR_FAILED.format(name=name, reason=calendar.rstrip(".")))
    return problems
