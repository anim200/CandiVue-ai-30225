"""Candidate API: the invited candidate's own interview, reached through the
private link (POST /api/auth/candidate gives a token for that one session).

Candidates only, and only their own interview: the token says which
session. They see the job, the time, the interviewer's name, the call and
the chat with the interviewer; never scores, rankings, transcripts, the CV
panel, the assistant or reports (N9).

Waiting room: the candidate's page sends a heartbeat while they wait; they
get a call ticket only after the interviewer let them in (checked here, not
only on the page). Once let in, a reload or a dropped connection goes
straight back into the call.
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_candidate
from app.core import clock
from app.db.database import get_db
from app.db.models import Candidate, InterviewSession, Job, User
from app.db.models.interview import InvitationStatus, SessionStatus, Speaker
from app.interviews import chat, room

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/candidate",
    tags=["candidate"],
    dependencies=[Depends(require_candidate)],
)

NOT_INVITED = "Your invitation has not been sent yet. Please use the link in the email."
NOT_LET_IN = "The interviewer has not let you in yet. Please wait in the waiting room."
OVER = {
    SessionStatus.ENDED: "The interview has ended.",
    SessionStatus.CANCELLED: "This interview was cancelled.",
}


class LobbyOut(BaseModel):
    """The waiting room as the candidate sees it."""

    interviewer_present: bool  # the interviewer has the room open
    admitted: bool  # let in: the call can start


class MyInterviewOut(BaseModel):
    """What the candidate may see about their interview."""

    job_title: str
    interviewer_name: str | None
    scheduled_at: datetime
    duration_minutes: int
    started_at: datetime | None
    status: SessionStatus
    lobby: LobbyOut


class TicketOut(BaseModel):
    """A ticket for the candidate's own video room."""

    token: str


class MessageIn(BaseModel):
    """A chat message to the interviewer."""

    text: str = Field(min_length=1, max_length=chat.MAX_LENGTH)


@router.get("/interview", response_model=MyInterviewOut)
def my_interview(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_candidate)],
) -> MyInterviewOut:
    """The candidate's interview: job, time, interviewer and whether it is
    still on."""
    return _out(db, db.get(InterviewSession, user.id))


@router.post("/waiting", response_model=MyInterviewOut)
def waiting(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_candidate)],
) -> MyInterviewOut:
    """Heartbeat from the waiting room (every few seconds): the interviewer
    sees that the candidate is waiting. Answers whether they were let in."""
    session = db.get(InterviewSession, user.id)
    if session.status not in OVER and session.admitted_at is None:
        session.candidate_waiting_at = clock.now()
        db.commit()
    return _out(db, session)


@router.post("/room", response_model=TicketOut)
def join_room(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_candidate)],
) -> TicketOut:
    """A ticket for the candidate's own video call: once the invitation was
    emailed and the interviewer let them in, until the interview ends."""
    session = _open(db, user.id)
    if session.admitted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_LET_IN)
    name = db.get(Candidate, session.candidate_id).full_name or "Candidate"
    try:
        token = room.ticket(session, f"candidate-{session.id}", name)
    except room.RoomError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from None
    return TicketOut(token=token)


@router.get("/messages")
def list_messages(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_candidate)],
    after: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    """The chat with the interviewer (only messages after `after`)."""
    session = _open(db, user.id)
    if session.admitted_at is None:
        return []  # the chat opens with the call
    return chat.history(db, session.id, after)


@router.post("/messages")
def send_message(
    body: MessageIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_candidate)],
) -> dict:
    """Send a chat message to the interviewer (only once let in)."""
    session = _open(db, user.id)
    if session.admitted_at is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_LET_IN)
    try:
        return chat.send(db, session, Speaker.CANDIDATE, body.text)
    except chat.ChatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


def _open(db: Session, session_id: int) -> InterviewSession:
    """The candidate's interview if it is still on and was emailed; 410 /
    409 otherwise."""
    session = db.get(InterviewSession, session_id)
    if session.status in OVER:
        raise HTTPException(status.HTTP_410_GONE, OVER[session.status])
    if session.invitation_status != InvitationStatus.SENT:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_INVITED)
    return session


def _out(db: Session, session: InterviewSession) -> MyInterviewOut:
    """The interview as the candidate's page shows it."""
    interviewer = (
        db.get(User, session.interviewer_id) if session.interviewer_id else None
    )
    lobby = room.lobby(session)
    return MyInterviewOut(
        job_title=db.get(Job, session.job_id).title,
        interviewer_name=interviewer.full_name if interviewer else None,
        scheduled_at=session.scheduled_at,
        duration_minutes=session.duration_minutes,
        started_at=session.started_at,
        status=session.status,
        lobby=LobbyOut(
            interviewer_present=lobby["interviewer_present"], admitted=lobby["admitted"]
        ),
    )
