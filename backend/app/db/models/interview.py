"""Interview sessions and transcripts (F3, F4)."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, status_column


class SessionStatus(StrEnum):
    """The life of an interview: scheduled, live, ended or cancelled."""

    SCHEDULED = "scheduled"
    LIVE = "live"
    ENDED = "ended"
    CANCELLED = "cancelled"


class InvitationStatus(StrEnum):
    """Whether the interview invitation is waiting, sent or failed."""

    PENDING = "pending"  # waiting for the interviewer to confirm
    SENT = "sent"
    FAILED = "failed"


class InterviewSession(TimestampMixin, Base):
    """One 1-on-1 interview between an interviewer and a candidate."""

    __tablename__ = "interview_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    interviewer_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Only a hash of the link token is stored, so a database leak does not
    # leak working interview links.
    join_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[SessionStatus] = mapped_column(
        status_column(SessionStatus), default=SessionStatus.SCHEDULED
    )
    invitation_status: Mapped[InvitationStatus] = mapped_column(
        status_column(InvitationStatus), default=InvitationStatus.PENDING
    )
    calendar_event_id: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Speaker(StrEnum):
    """Who said a transcript line: the interviewer or the candidate."""

    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class TranscriptTurn(TimestampMixin, Base):
    """One utterance. Times are milliseconds from the start of the interview."""

    __tablename__ = "transcript_turns"
    __table_args__ = (Index(None, "session_id", "start_ms"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    speaker: Mapped[Speaker] = mapped_column(status_column(Speaker))
    text: Mapped[str] = mapped_column(Text)
    start_ms: Mapped[int]
    end_ms: Mapped[int]
