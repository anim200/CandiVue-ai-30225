"""Candidate API: the invited candidate's own interview, reached through the
private link (POST /api/auth/candidate gives a token for that one session).

Candidates only, and only their own interview: the token says which
session. They see the job, the time and the call, never scores, rankings,
transcripts or reports (N9).
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_candidate
from app.db.database import get_db
from app.db.models import Candidate, InterviewSession, Job
from app.db.models.interview import InvitationStatus, SessionStatus
from app.interviews import room

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/candidate",
    tags=["candidate"],
    dependencies=[Depends(require_candidate)],
)

NOT_INVITED = "Your invitation has not been sent yet. Please use the link in the email."
OVER = {
    SessionStatus.ENDED: "The interview has ended.",
    SessionStatus.CANCELLED: "This interview was cancelled.",
}


class MyInterviewOut(BaseModel):
    """What the candidate may see about their interview."""

    job_title: str
    scheduled_at: datetime
    duration_minutes: int
    status: SessionStatus


class TicketOut(BaseModel):
    """A ticket for the candidate's own video room."""

    token: str


@router.get("/interview", response_model=MyInterviewOut)
def my_interview(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_candidate)],
) -> MyInterviewOut:
    """The candidate's interview: job, time and whether it is still on."""
    session = db.get(InterviewSession, user.id)
    return MyInterviewOut(
        job_title=db.get(Job, session.job_id).title,
        scheduled_at=session.scheduled_at,
        duration_minutes=session.duration_minutes,
        status=session.status,
    )


@router.post("/room", response_model=TicketOut)
def join_room(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_candidate)],
) -> TicketOut:
    """A ticket for the candidate's own video call: any time until the
    interviewer ends it, once the invitation email was sent."""
    session = db.get(InterviewSession, user.id)
    if session.status in OVER:
        raise HTTPException(status.HTTP_410_GONE, OVER[session.status])
    if session.invitation_status != InvitationStatus.SENT:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_INVITED)
    name = db.get(Candidate, session.candidate_id).full_name or "Candidate"
    try:
        token = room.ticket(session, f"candidate-{session.id}", name)
    except room.RoomError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    return TicketOut(token=token)
