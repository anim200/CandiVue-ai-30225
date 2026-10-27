"""Interviews API: the Interviews page lists the scheduled and past
interviews, (re)sends the invitation email and cancels an interview; the
interviewer joins the video call (a ticket for its LiveKit room) and ends
it. Sending and cancelling also update the interviewer's Google Calendar.

Interviewers only (N9). Interviews are created from the Hiring Assistant
after the interviewer confirms them (§4B-7b). The email is the only way a
candidate gets their private link, and nobody can join the call before it
was sent. Only a hash of each link is stored, so sending the email again
makes a new link; the previous one stops working.

In the room: the interviewer's page sends a heartbeat (presence) and sees
whether the candidate waits; "Let in" admits them (the candidate's ticket
needs it). The chat with the candidate, the candidate's CV panel and the
live transcript (F4, written by the transcriber service) are here too, and
the identity check (F7, §4B-15): the application photo, the check-in result
with its match score and, on a match only, a short profile. The waiting
room's heartbeat carries the same result, so it is seen before "Let in".
"""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_interviewer
from app.core import clock
from app.db.database import get_db
from app.db.models import Candidate, InterviewSession, Job, TranscriptTurn, User
from app.db.models.interview import InvitationStatus, SessionStatus, Speaker
from app.graphs import qa_analysis
from app.identity.matching import identity_view
from app.identity.references import photo_state, thumbnail
from app.interviews import calendar_sync, chat, cv_view, emails, planning, room

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/interviews",
    tags=["interviews"],
    dependencies=[Depends(require_interviewer)],
)

NOT_FOUND = "This interview no longer exists."
NO_PHOTO = "There is no usable application photo for this candidate."
# A live interview without the transcriber for this long: it is not running.
TRANSCRIBER_GRACE_SECONDS = 30
# Turns changed shortly before `since` are sent again (clocks and slow
# saves); the page merges them by id.
SINCE_OVERLAP = timedelta(seconds=3)
NOT_ACTIVE = "This interview has ended or was cancelled."
NOT_INVITED = (
    "The candidate has not been emailed the invitation yet: send it first "
    "(Interviews page), then join."
)


class InterviewOut(BaseModel):
    """One interview in the list."""

    id: int
    candidate_id: int
    candidate_name: str
    job_id: int
    job_title: str
    scheduled_at: datetime
    duration_minutes: int
    status: SessionStatus
    invitation_status: InvitationStatus
    invitation_error: str | None  # why the last email failed
    started_at: datetime | None  # when the call first opened (Live)
    ended_at: datetime | None
    interviewer_name: str | None  # who took part (or was planned)
    admitted: bool  # the candidate was let in from the waiting room
    photo: str  # the application photo (F7): ready, missing, pending, ...


class LobbyOut(BaseModel):
    """The waiting room: is the candidate waiting, were they let in, and
    their check-in result (F7) for the "Let in" banner."""

    interviewer_present: bool
    candidate_waiting: bool
    admitted: bool
    status: SessionStatus
    identity: dict | None = None  # {"state", "text", "score"} while waiting


class TurnOut(BaseModel):
    """One transcript turn: who, what, and when (ms from the start)."""

    id: int
    speaker: Speaker
    text: str
    start_ms: int
    end_ms: int


class TranscriptOut(BaseModel):
    """The live transcript: turns new or changed since `since`, the time to
    ask from next, and whether speech-to-text is working."""

    turns: list[TurnOut]
    server_time: datetime
    status: Literal["waiting", "starting", "listening", "off", "problem", "ended"]
    problem: str | None


class MessageIn(BaseModel):
    """A chat message to the candidate."""

    text: str = Field(min_length=1, max_length=chat.MAX_LENGTH)


class SendOut(BaseModel):
    """The result of sending the invitation email."""

    sent: bool
    message: str  # "Invitation sent" or why it failed
    calendar: str | None  # "added" / "moved", or why the calendar failed


class CancelOut(BaseModel):
    """The result of a cancellation: the candidate's email and the calendar
    ("sent" / "removed", why it failed, or None: nothing to do)."""

    email: str | None
    calendar: str | None


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
    session.interviewer_seen_at = clock.now()  # the candidate sees "here"
    db.commit()
    return TicketOut(token=token)


@router.post("/{interview_id}/presence", response_model=LobbyOut)
def presence(interview_id: int, db: Annotated[Session, Depends(get_db)]) -> LobbyOut:
    """Heartbeat from the interviewer's open room page (every few seconds);
    answers whether the candidate is waiting to be let in."""
    session = _found(db, interview_id)
    if session.status in planning.ACTIVE:
        session.interviewer_seen_at = clock.now()
        db.commit()
    lobby = room.lobby(session)
    waiting = None
    if lobby["candidate_waiting"]:
        view = identity_view(db, session)
        waiting = {key: view[key] for key in ("state", "text", "score")}
    return LobbyOut(**lobby, status=session.status, identity=waiting)


@router.post("/{interview_id}/admit", response_model=LobbyOut)
def admit(interview_id: int, db: Annotated[Session, Depends(get_db)]) -> LobbyOut:
    """Let the candidate in from the waiting room. Once let in, they can
    rejoin after a dropped connection without asking again."""
    session = _active(db, interview_id)
    if session.invitation_status != InvitationStatus.SENT:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_INVITED)
    if session.admitted_at is None:
        session.admitted_at = clock.now()
        db.commit()
        logger.info("Candidate let in: session %d", interview_id)
    return LobbyOut(**room.lobby(session), status=session.status)


@router.get("/{interview_id}/candidate")
def candidate_cv(interview_id: int, db: Annotated[Session, Depends(get_db)]) -> dict:
    """The candidate's CV panel in the room: parsed facts and screening."""
    return cv_view.overview(db, _found(db, interview_id))


@router.get("/{interview_id}/transcript", response_model=TranscriptOut)
def transcript(
    interview_id: int,
    db: Annotated[Session, Depends(get_db)],
    since: datetime | None = None,
) -> TranscriptOut:
    """The live transcript (interviewers only; candidates never see it, N9):
    every turn, or only those new or changed since `since` (a growing turn
    changes while the person speaks)."""
    session = _found(db, interview_id)
    now = clock.now()
    query = select(TranscriptTurn).where(TranscriptTurn.session_id == session.id)
    if since is not None:
        query = query.where(TranscriptTurn.updated_at > since - SINCE_OVERLAP)
    turns = db.scalars(query.order_by(TranscriptTurn.start_ms, TranscriptTurn.id))
    state, problem = _transcript_status(session, now)
    return TranscriptOut(
        turns=[TurnOut.model_validate(t, from_attributes=True) for t in turns],
        server_time=now,
        status=state,
        problem=problem,
    )


@router.get("/{interview_id}/identity")
def identity(interview_id: int, db: Annotated[Session, Depends(get_db)]) -> dict:
    """The identity check (F7): the check-in result against the application
    photo, with its match score; the profile only on a match."""
    return identity_view(db, _found(db, interview_id))


@router.get("/{interview_id}/identity/photo")
def identity_photo(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """The small copy of the application photo, for the interviewer to
    compare with the video (never cached by the browser)."""
    session = _found(db, interview_id)
    jpeg = thumbnail(db, session.candidate_id)
    if jpeg is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_PHOTO)
    return Response(
        jpeg, media_type="image/jpeg", headers={"Cache-Control": "no-store"}
    )


@router.get("/{interview_id}/messages")
def list_messages(
    interview_id: int,
    db: Annotated[Session, Depends(get_db)],
    after: Annotated[int, Query(ge=0)] = 0,
) -> list[dict]:
    """The chat with the candidate (only messages after `after`)."""
    return chat.history(db, _found(db, interview_id).id, after)


@router.post("/{interview_id}/messages")
def send_message(
    interview_id: int, body: MessageIn, db: Annotated[Session, Depends(get_db)]
) -> dict:
    """Send a chat message to the candidate."""
    session = _active(db, interview_id)
    try:
        return chat.send(db, session, Speaker.INTERVIEWER, body.text)
    except chat.ChatError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None


@router.post("/{interview_id}/end", response_model=InterviewOut)
def end_interview(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> InterviewOut:
    """End the interview: it is saved as ended with its end time, the call
    closes for everyone and the candidate's link stops working. The Q&A
    analysis (F5) starts, and after it the assessment report (F6)."""
    session = _active(db, interview_id)
    session.status = SessionStatus.ENDED
    session.ended_at = clock.now()
    db.commit()
    room.end_room(session.id)
    logger.info("Interview ended: session %d", interview_id)
    qa_analysis.start_analysis(db, session.id)
    return _out(db, session)


@router.post("/{interview_id}/send", response_model=SendOut)
def send_invitation(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> SendOut:
    """Email the invitation (again) with a new private link, and put the
    interview in the calendar if it is not there yet."""
    session = _active(db, interview_id)
    token, session.join_token_hash = planning.new_link_token()
    text, _ = emails.template(db)
    problem = emails.deliver(db, session, token, text)
    calendar = calendar_sync.sync(db, session)
    db.commit()
    return SendOut(
        sent=problem is None, message=problem or "Invitation sent", calendar=calendar
    )


@router.post("/{interview_id}/cancel", response_model=CancelOut)
def cancel(interview_id: int, db: Annotated[Session, Depends(get_db)]) -> CancelOut:
    """Cancel a scheduled interview: its link stops working, an open call is
    closed, the candidate is emailed (if invited) and the calendar event is
    removed."""
    session = _active(db, interview_id)
    session.status = SessionStatus.CANCELLED
    db.commit()
    room.end_room(interview_id)
    logger.info("Interview cancelled: session %d", interview_id)
    email = planning.cancel_notice(db, session)
    calendar = calendar_sync.sync(db, session)
    db.commit()
    return CancelOut(email=email, calendar=calendar)


def _transcript_status(
    session: InterviewSession, now: datetime
) -> tuple[str, str | None]:
    """Whether speech-to-text works for this interview, and why not."""
    if session.status in (SessionStatus.ENDED, SessionStatus.CANCELLED):
        return "ended", None
    if session.status == SessionStatus.SCHEDULED:
        return "waiting", None
    if session.transcript_problem:
        return "problem", session.transcript_problem
    if room.is_present(session.transcriber_seen_at):
        return "listening", None
    started = session.started_at
    if started and now - started > timedelta(seconds=TRANSCRIBER_GRACE_SECONDS):
        return "off", None
    return "starting", None


def _out(db: Session, session: InterviewSession) -> InterviewOut:
    """An interview as the pages show it."""
    candidate = db.get(Candidate, session.candidate_id)
    interviewer = (
        db.get(User, session.interviewer_id) if session.interviewer_id else None
    )
    return InterviewOut(
        id=session.id,
        candidate_id=candidate.id,
        candidate_name=candidate.full_name or candidate.cv_filename,
        job_id=session.job_id,
        job_title=db.get(Job, session.job_id).title,
        scheduled_at=session.scheduled_at,
        duration_minutes=session.duration_minutes,
        status=session.status,
        invitation_status=session.invitation_status,
        invitation_error=session.invitation_error,
        started_at=session.started_at,
        ended_at=session.ended_at,
        interviewer_name=interviewer.full_name if interviewer else None,
        admitted=session.admitted_at is not None,
        photo=photo_state(db, candidate),
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
