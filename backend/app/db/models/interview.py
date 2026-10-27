"""Interview sessions, transcripts and application photos (F3, F4, F7)."""

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
    # Identity check at check-in (F7, §4B-15): the candidate's choice and
    # the result of comparing their camera pictures with the application
    # photo ({"state", "score", "similarity", "other", "checked_at",
    # "attempts"}). Never shown to the candidate (N9).
    identity_consent: Mapped[IdentityConsent | None] = mapped_column(
        status_column(IdentityConsent)
    )
    identity_consent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    identity_result: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


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


class PhotoStatus(StrEnum):
    """What came of the photo sent with the application (F7, §4B-15)."""

    READY = "ready"  # one clear face: embedding and small copy saved
    NO_FACE = "no_face"
    SEVERAL_FACES = "several_faces"
    TOO_SMALL = "too_small"  # the face is too small to compare
    UNREADABLE = "unreadable"  # not an image we can read
    TOO_LARGE = "too_large"
    DOWNLOAD_FAILED = "download_failed"  # tried again in later rounds


class ApplicationPhoto(TimestampMixin, Base):
    """The face photo an invited applicant sent with the Google Form (F7,
    §4B-15), processed by the CV Collector: the encrypted face embedding
    (128 numbers) and a small encrypted copy for the interviewer, never the
    original file. Deleted RETENTION days after the interview, when it is
    cancelled, and with the candidate or job (N17, N19)."""

    __tablename__ = "application_photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[PhotoStatus] = mapped_column(status_column(PhotoStatus))
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)  # Fernet-encrypted
    thumbnail: Mapped[bytes | None] = mapped_column(
        LargeBinary
    )  # Fernet-encrypted JPEG
    tries: Mapped[int] = mapped_column(default=0, server_default="0")
