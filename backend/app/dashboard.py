"""The home page (dashboard): what needs the interviewer now, in one call.

- counts: open jobs, applications in the last 7 days, CVs waiting for a
  screening, interviews today, reports waiting for review, candidates
  selected this month;
- next steps, most urgent first: interviews live now, interviews today,
  reports to review, jobs whose CVs need a (new) screening;
- the next interviews, and applications per day for the last 14 days.

It only reads and counts; every action stays on its own page (and the
Hiring Assistant), so nothing here changes data. Interviewers only (N9).
Days are local days (APP_TIMEZONE).
"""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import (
    AssessmentReport,
    Candidate,
    InterviewSession,
    Job,
    ScreeningRun,
)
from app.db.models.assessment import ReviewStatus
from app.db.models.candidate import CandidateStatus
from app.db.models.interview import SessionStatus
from app.db.models.job import JobStatus
from app.db.models.run import RunStatus
from app.interviews import ranking

MAX_STEPS = 8
MAX_UPCOMING = 5
CHART_DAYS = 14
ACTIVE = (SessionStatus.SCHEDULED, SessionStatus.LIVE)
SCREENING = (RunStatus.PENDING, RunStatus.RUNNING)


def summary(db: Session) -> dict:
    """Everything the home page shows."""
    now = clock.now()
    today = _local_day_start(now)
    return {
        "counts": _counts(db, now, today),
        "next_steps": _next_steps(db, today)[:MAX_STEPS],
        "upcoming": _upcoming(db, today),
        "applications": applications_by_day(db, today),
    }


def applications_by_day(db: Session, today: datetime) -> list[dict]:
    """Applications (usable CVs) per local day, oldest first, ending today."""
    first = today - timedelta(days=CHART_DAYS - 1)
    zone = clock.local_zone()
    per_day = {(first + timedelta(days=i)).date(): 0 for i in range(CHART_DAYS)}
    for created in db.scalars(
        select(Candidate.created_at).where(
            Candidate.created_at >= first, Candidate.status != CandidateStatus.REJECTED
        )
    ):
        day = created.astimezone(zone).date()
        if day in per_day:
            per_day[day] += 1
    return [{"day": day.isoformat(), "count": count} for day, count in per_day.items()]


def cvs_to_screen(db: Session, job: Job) -> int:
    """The job's usable CVs not in a screening yet (0 while one is running)."""
    run = db.scalar(
        select(ScreeningRun)
        .where(ScreeningRun.job_id == job.id)
        .order_by(ScreeningRun.id.desc())
        .limit(1)
    )
    if run is None:
        return db.scalar(
            select(func.count(Candidate.id)).where(
                Candidate.job_id == job.id, Candidate.status != CandidateStatus.REJECTED
            )
        )
    if run.status in SCREENING:
        return 0
    return ranking.new_cv_count(db, job, run)


def _counts(db: Session, now: datetime, today: datetime) -> dict:
    """The numbers on the cards."""
    month = today.replace(day=1)
    open_jobs = list(db.scalars(select(Job).where(Job.status == JobStatus.OPEN)))
    return {
        "open_jobs": len(open_jobs),
        "applications_week": db.scalar(
            select(func.count(Candidate.id)).where(
                Candidate.created_at >= now - timedelta(days=7),
                Candidate.status != CandidateStatus.REJECTED,
            )
        ),
        "cvs_to_screen": sum(cvs_to_screen(db, job) for job in open_jobs),
        "interviews_today": len(_today_sessions(db, today)),
        "reports_to_review": len(_reports_to_review(db)),
        "selected_month": db.scalar(
            select(func.count(Candidate.id)).where(Candidate.selected_at >= month)
        ),
    }


def _next_steps(db: Session, today: datetime) -> list[dict]:
    """What needs the interviewer, most urgent first."""
    steps = []
    for session, name, job in _today_sessions(db, today):
        live = session.status == SessionStatus.LIVE
        steps.append(
            {
                "kind": "live" if live else "interview",
                "text": f"Interview with {name} is live now"
                if live
                else f"Interview with {name} at {_time(session.scheduled_at)}",
                "detail": job.title,
                "action": "Rejoin" if live else "Join",
                "link": f"/interviews/{session.id}/room",
            }
        )
    for session, name, job in _reports_to_review(db):
        steps.append(
            {
                "kind": "review",
                "text": f"Review the report for {name}",
                "detail": job.title,
                "action": "Review",
                "link": f"/interviews/{session.id}/report",
            }
        )
    for job in db.scalars(
        select(Job).where(Job.status == JobStatus.OPEN).order_by(Job.id)
    ):
        step = _job_step(db, job)
        if step:
            steps.append(step)
    return steps


def _job_step(db: Session, job: Job) -> dict | None:
    """A job whose CVs need a screening: new CVs, or the deadline passed
    after the last screening (invitations need a screening after it)."""
    new = cvs_to_screen(db, job)
    closes = job.applications_close_at
    run = db.scalar(
        select(ScreeningRun)
        .where(
            ScreeningRun.job_id == job.id, ScreeningRun.status == RunStatus.COMPLETED
        )
        .order_by(ScreeningRun.id.desc())
        .limit(1)
    )
    closed_since = (
        closes is not None
        and closes <= clock.now()
        and run is not None
        and run.created_at < closes
    )
    if not new and not closed_since:
        return None
    text = (
        f"Applications for {job.title} have closed: screen again before inviting"
        if closed_since
        else f"{new} new CV{'s' if new != 1 else ''} to screen for {job.title}"
    )
    return {
        "kind": "screen",
        "text": text,
        "detail": job.title,
        "action": "Screen CVs",
        "link": f"/jobs/{job.id}",
    }


def _upcoming(db: Session, today: datetime) -> list[dict]:
    """The next interviews (from the start of today), soonest first."""
    rows = db.execute(
        select(InterviewSession, Candidate.full_name, Candidate.cv_filename, Job.title)
        .join(Candidate, Candidate.id == InterviewSession.candidate_id)
        .join(Job, Job.id == InterviewSession.job_id)
        .where(
            InterviewSession.status.in_(ACTIVE), InterviewSession.scheduled_at >= today
        )
        .order_by(InterviewSession.scheduled_at)
        .limit(MAX_UPCOMING)
    ).all()
    return [
        {
            "id": session.id,
            "candidate_name": name or filename,
            "job_title": title,
            "scheduled_at": session.scheduled_at,
            "status": session.status,
            "invitation_status": session.invitation_status,
        }
        for session, name, filename, title in rows
    ]


def _today_sessions(db: Session, today: datetime) -> list[tuple]:
    """Interviews live now or scheduled for today: (session, name, job)."""
    rows = db.execute(
        select(InterviewSession, Candidate, Job)
        .join(Candidate, Candidate.id == InterviewSession.candidate_id)
        .join(Job, Job.id == InterviewSession.job_id)
        .where(InterviewSession.status.in_(ACTIVE))
        .order_by(InterviewSession.scheduled_at)
    ).all()
    tomorrow = today + timedelta(days=1)
    return [
        (session, candidate.full_name or candidate.cv_filename, job)
        for session, candidate, job in rows
        if session.status == SessionStatus.LIVE
        or today <= session.scheduled_at < tomorrow
    ]


def _reports_to_review(db: Session) -> list[tuple]:
    """Ended interviews whose latest report waits for review: (session, name, job)."""
    latest = (
        select(func.max(AssessmentReport.id))
        .group_by(AssessmentReport.session_id)
        .scalar_subquery()
    )
    rows = db.execute(
        select(InterviewSession, Candidate, Job)
        .join(AssessmentReport, AssessmentReport.session_id == InterviewSession.id)
        .join(Candidate, Candidate.id == InterviewSession.candidate_id)
        .join(Job, Job.id == InterviewSession.job_id)
        .where(
            AssessmentReport.id.in_(latest),
            AssessmentReport.status == RunStatus.WAITING_FOR_REVIEW,
            AssessmentReport.review_status == ReviewStatus.PENDING_REVIEW,
        )
        .order_by(InterviewSession.ended_at)
    ).all()
    return [
        (session, candidate.full_name or candidate.cv_filename, job)
        for session, candidate, job in rows
    ]


def _local_day_start(moment: datetime) -> datetime:
    """Midnight (local) of the day the moment falls on, as an aware time."""
    local = moment.astimezone(clock.local_zone())
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _time(moment: datetime) -> str:
    """A time of day as people read it, e.g. "10:30"."""
    return moment.astimezone(clock.local_zone()).strftime("%H:%M")
