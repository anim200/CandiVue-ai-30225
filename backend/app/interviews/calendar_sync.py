"""Interviews and the interviewer's Google Calendar (§4B-8).

busy_times() gives the calendar's busy periods for the scheduling checks.
Events that are CandiVue interviews are left out: those are already checked
from the database (with a clearer label), and a moved interview must not
clash with its own old time.

sync() makes the calendar match one interview after it was confirmed, sent
again or cancelled: add the event (its id is saved on the session), move
it, or delete it. Candidates are never guests (they get the invite with the
email). A calendar failure never undoes the interview: it is reported, and
"Resend" on the Interviews page tries again.
"""

import logging
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import Candidate, InterviewSession, Job
from app.db.models.interview import SessionStatus
from app.integrations import calendar
from app.integrations.calendar import CalendarError

logger = logging.getLogger(__name__)

UNCHECKED = (
    "Your calendar could not be checked ({reason}): only your CandiVue interviews were."
)


def busy_times(db: Session, start: datetime, end: datetime) -> tuple[list, str | None]:
    """Busy periods in the calendar: ([(start, end, label)], warning). The
    warning says the calendar could not be checked (the list is then empty)."""
    try:
        found = calendar.busy(start, end)
    except CalendarError as exc:
        return [], UNCHECKED.format(reason=str(exc).rstrip("."))
    ours = set(
        db.scalars(
            select(InterviewSession.calendar_event_id).where(
                InterviewSession.calendar_event_id.is_not(None)
            )
        )
    )
    periods = []
    for event in found:
        if event["event_id"] in ours:
            continue
        b_start = datetime.fromisoformat(event["start"])
        b_end = datetime.fromisoformat(event["end"])
        hours = (
            f"{b_start.astimezone(clock.local_zone()):%H:%M}–"
            f"{b_end.astimezone(clock.local_zone()):%H:%M}"
        )
        periods.append((b_start, b_end, f"a busy time in your calendar ({hours})"))
    return periods, None


def sync(db: Session, session: InterviewSession) -> str | None:
    """Make the calendar match the interview; returns what happened
    ("added", "moved", "removed"), why it failed, or None when there was
    nothing to do. The caller commits."""
    end = session.scheduled_at + timedelta(minutes=session.duration_minutes)
    try:
        if session.status == SessionStatus.CANCELLED:
            if not session.calendar_event_id:
                return None  # was never in the calendar
            calendar.delete_event(session.calendar_event_id)
            session.calendar_event_id = None
            done = "removed"
        elif session.calendar_event_id:
            calendar.move_event(session.calendar_event_id, session.scheduled_at, end)
            done = "moved"
        else:
            summary, description = _summary_and_description(db, session)
            session.calendar_event_id = calendar.add_event(
                summary, session.scheduled_at, end, description
            )
            done = "added"
    except CalendarError as exc:
        logger.warning("Calendar not updated: session %d", session.id)
        return str(exc)
    logger.info("Calendar %s: session %d", done, session.id)
    return done


def _summary_and_description(db: Session, session: InterviewSession) -> tuple[str, str]:
    """The event's title and text: who, which job, and where to join."""
    candidate = db.get(Candidate, session.candidate_id)
    job = db.get(Job, session.job_id)
    name = candidate.full_name or "a candidate"
    room = f"{get_settings().app_public_url.rstrip('/')}/interviews/{session.id}/room"
    return (
        f"Interview: {name} ({job.title})",
        f"CandiVue interview with {name} for {job.title}.\nJoin the call: {room}",
    )
