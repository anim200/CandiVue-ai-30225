"""Interviews API: the Interviews page lists the scheduled and past
interviews, (re)sends the invitation email and cancels an interview; the
interviewer joins the video call (a ticket for its LiveKit room) and ends
it.

Interviewers only (N9). Interviews are created from the Hiring Assistant
after the interviewer confirms them (§4B-7b). The email is the only way a
candidate gets their private link, and nobody can join the call before it
was sent. Only a hash of each link is stored, so sending the email again
makes a new link; the previous one stops working.
"""

import logging
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_interviewer
from app.core import clock
from app.db.database import get_db
from app.db.models import Candidate, InterviewSession, Job, User
from app.db.models.interview import InvitationStatus, SessionStatus
from app.interviews import emails, planning, room

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/interviews",
    tags=["interviews"],
    dependencies=[Depends(require_interviewer)],
)

NOT_FOUND = "This interview no longer exists."
NOT_ACTIVE = "This interview has ended or was cancelled."
NOT_INVITED = (
    "The candidate has not been emailed the invitation yet: send it first "
    "(Interviews page), then join."
)


class InterviewOut(BaseModel):
    """One interview in the list."""

    id: int
    candidate_name: str
    job_id: int
    job_title: str
    scheduled_at: datetime
    duration_minutes: int
    status: SessionStatus
    invitation_status: InvitationStatus


class SendOut(BaseModel):
    """The result of sending the invitation email."""

    sent: bool
    message: str  # "Invitation sent" or why it failed


class TicketOut(BaseModel):
    """A ticket for the interview's video room (valid for that room only)."""

    token: str


@router.get("", response_model=list[InterviewOut])
def list_interviews(
    db: Annotated[Session, Depends(get_db)],
    when: Literal["upcoming", "past"] = "upcoming",
) -> list[InterviewOut]:
    """Upcoming (scheduled or live, soonest first) or past (ended or
    cancelled, newest first) interviews."""
    upcoming = when == "upcoming"
    statuses = (
        planning.ACTIVE if upcoming else (SessionStatus.ENDED, SessionStatus.CANCELLED)
    )
    order = InterviewSession.scheduled_at
    rows = db.scalars(
        select(InterviewSession)
        .where(InterviewSession.status.in_(statuses))
        .order_by(order if upcoming else order.desc())
    )
    return [_out(db, session) for session in rows]


@router.get("/{interview_id}", response_model=InterviewOut)
def get_interview(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> InterviewOut:
    """One interview (for its video room page)."""
    return _out(db, _found(db, interview_id))


@router.post("/{interview_id}/room", response_model=TicketOut)
def join_room(
    interview_id: int,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_interviewer)],
) -> TicketOut:
    """A ticket for the interviewer to join the video call: any time until
    the interview ends, once the invitation email was sent."""
    session = _active(db, interview_id)
    if session.invitation_status != InvitationStatus.SENT:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_INVITED)
    name = db.get(User, user.id).full_name
    try:
        token = room.ticket(session, f"interviewer-{user.id}", name)
    except room.RoomError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    return TicketOut(token=token)


@router.post("/{interview_id}/end", response_model=InterviewOut)
def end_interview(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> InterviewOut:
    """End the interview: it is saved as ended with its end time, the call
    closes for everyone and the candidate's link stops working."""
    session = _active(db, interview_id)
    session.status = SessionStatus.ENDED
    session.ended_at = clock.now()
    db.commit()
    room.end_room(session.id)
    logger.info("Interview ended: session %d", interview_id)
    return _out(db, session)


@router.post("/{interview_id}/send", response_model=SendOut)
def send_invitation(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> SendOut:
    """Email the invitation (again) with a new private link."""
    session = _active(db, interview_id)
    token, session.join_token_hash = planning.new_link_token()
    text, _ = emails.template(db)
    problem = emails.deliver(db, session, token, text)
    db.commit()
    return SendOut(sent=problem is None, message=problem or "Invitation sent")


@router.post("/{interview_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel(interview_id: int, db: Annotated[Session, Depends(get_db)]) -> None:
    """Cancel a scheduled interview (its link stops working and an open
    call is closed)."""
    _active(db, interview_id).status = SessionStatus.CANCELLED
    db.commit()
    room.end_room(interview_id)
    logger.info("Interview cancelled: session %d", interview_id)


def _out(db: Session, session: InterviewSession) -> InterviewOut:
    """An interview as the pages show it."""
    candidate = db.get(Candidate, session.candidate_id)
    return InterviewOut(
        id=session.id,
        candidate_name=candidate.full_name or candidate.cv_filename,
        job_id=session.job_id,
        job_title=db.get(Job, session.job_id).title,
        scheduled_at=session.scheduled_at,
        duration_minutes=session.duration_minutes,
        status=session.status,
        invitation_status=session.invitation_status,
    )


def _found(db: Session, interview_id: int) -> InterviewSession:
    """The interview, or 404."""
    session = db.get(InterviewSession, interview_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return session


def _active(db: Session, interview_id: int) -> InterviewSession:
    """The interview if it is still scheduled or live; 404 / 409 otherwise."""
    session = _found(db, interview_id)
    if session.status not in planning.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ACTIVE)
    return session
