"""Interviews API: the Interviews page lists the scheduled and past
interviews, (re)sends the invitation email, makes a candidate's private
link and cancels an interview.

Interviewers only (N9). Interviews are created from the Hiring Assistant
after the interviewer confirms them (§4B-7b). Only a hash of each link is
stored, so sending the email or "Copy link" makes a new link; the previous
one (also an emailed one) stops working.
"""

import logging
from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import require_interviewer
from app.db.database import get_db
from app.db.models import Candidate, InterviewSession, Job
from app.db.models.interview import InvitationStatus, SessionStatus
from app.interviews import emails, planning

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/interviews",
    tags=["interviews"],
    dependencies=[Depends(require_interviewer)],
)

NOT_FOUND = "This interview no longer exists."
NOT_ACTIVE = "This interview has ended or was cancelled."


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


class LinkOut(BaseModel):
    """A new private link token (the page builds the link: /join/<token>)."""

    link_token: str


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
    rows = db.execute(
        select(InterviewSession, Candidate, Job)
        .join(Candidate, Candidate.id == InterviewSession.candidate_id)
        .join(Job, Job.id == InterviewSession.job_id)
        .where(InterviewSession.status.in_(statuses))
        .order_by(order if upcoming else order.desc())
    )
    return [
        InterviewOut(
            id=session.id,
            candidate_name=candidate.full_name or candidate.cv_filename,
            job_id=job.id,
            job_title=job.title,
            scheduled_at=session.scheduled_at,
            duration_minutes=session.duration_minutes,
            status=session.status,
            invitation_status=session.invitation_status,
        )
        for session, candidate, job in rows
    ]


@router.post("/{interview_id}/link", response_model=LinkOut)
def new_link(interview_id: int, db: Annotated[Session, Depends(get_db)]) -> LinkOut:
    """Make a new private link for the candidate (the old one stops working)."""
    session = _active(db, interview_id)
    token, session.join_token_hash = planning.new_link_token()
    db.commit()
    logger.info("New interview link: session %d", interview_id)
    return LinkOut(link_token=token)


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
    """Cancel a scheduled interview (its link stops working)."""
    _active(db, interview_id).status = SessionStatus.CANCELLED
    db.commit()
    logger.info("Interview cancelled: session %d", interview_id)


def _active(db: Session, interview_id: int) -> InterviewSession:
    """The interview if it is still scheduled or live; 404 / 409 otherwise."""
    session = db.get(InterviewSession, interview_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if session.status not in planning.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ACTIVE)
    return session
