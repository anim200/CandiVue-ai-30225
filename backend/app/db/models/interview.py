"""Interview sessions, transcripts and face references (F3, F4, F7)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import JSONB
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


class IdentityConsent(StrEnum):
    """The candidate's choice about face identification (F7)."""

    GIVEN = "given"
    DECLINED = "declined"  # declined, or withdrawn later


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
    duration_minutes: Mapped[int] = mapped_column(default=45, server_default="45")
    # Only a hash of the link token is stored, so a database leak does not
    # leak working interview links.
    join_token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[SessionStatus] = mapped_column(
        status_column(SessionStatus), default=SessionStatus.SCHEDULED
    )
    invitation_status: Mapped[InvitationStatus] = mapped_column(
        status_column(InvitationStatus), default=InvitationStatus.PENDING
    )
    invitation_error: Mapped[str | None] = mapped_column(String(300))  # why it failed
    calendar_event_id: Mapped[str | None] = mapped_column(String(200))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Waiting room: the candidate waits until the interviewer lets them in.
    # The two "seen" times are heartbeats from each side's open page, so
    # each side knows whether the other is there (a closed tab stops them).
    interviewer_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    candidate_waiting_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Interview questions made from the CV, kept so they are made once per
    # interview: {"model", "made_at", "questions": [...]}.
    cv_questions: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Live transcript (F4): the transcriber's heartbeat while it listens, and
    # why it cannot transcribe (safe to show), e.g. a refused Deepgram key.
    transcriber_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    transcript_problem: Mapped[str | None] = mapped_column(String(200))
    # Email access code: opening the link sends a one-time code to the
    # candidate's email; only its keyed hash is stored.
    access_code_hash: Mapped[str | None] = mapped_column(String(64))
    access_code_sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    access_code_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    access_code_tries: Mapped[int] = mapped_column(default=0, server_default="0")
    # Identity check (F7): the candidate's consent, the latest live result
    # ({"state", "similarity", "other", "checked_at", "confirmed_at_ms"})
    # and when the interviewer last asked to check again.
    identity_consent: Mapped[IdentityConsent | None] = mapped_column(
        status_column(IdentityConsent)
    )
    identity_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    identity_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    identity_recheck_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )


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


class InterviewMessage(TimestampMixin, Base):
    """One chat message between the interviewer and the candidate during
    the interview (plain text). Deleted with the interview (N19)."""

    __tablename__ = "interview_messages"
    __table_args__ = (Index(None, "session_id", "id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE")
    )
    sender: Mapped[Speaker] = mapped_column(status_column(Speaker))
    text: Mapped[str] = mapped_column(Text)


class FaceReference(TimestampMixin, Base):
    """The face reference a candidate gave with consent before the interview
    (F7): only the encrypted face embedding (128 numbers), never a photo.
    Deleted when the candidate withdraws, RETENTION days after the
    interview, when it is cancelled, and with the interview or candidate
    (N17, N19)."""

    __tablename__ = "face_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    embedding: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet-encrypted
