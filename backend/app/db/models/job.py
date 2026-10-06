"""Job profiles and their job descriptions (F1, Hiring Assistant)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, status_column


class JobStatus(StrEnum):
    """Whether a job is a draft, open or closed."""

    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"


class JobBoardStatus(StrEnum):
    """Whether the job has been posted to the job board."""

    NOT_POSTED = "not_posted"
    POSTED = "posted"
    FAILED = "failed"


class Job(TimestampMixin, Base):
    """One job opening and its requirement profile."""

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    # Required/preferred skills, qualifications, minimum years of experience,
    # must-haves and other selection criteria. Shape checked by Pydantic.
    profile: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[JobStatus] = mapped_column(
        status_column(JobStatus), default=JobStatus.DRAFT
    )
    google_form_url: Mapped[str | None] = mapped_column(String(500))
    job_board_status: Mapped[JobBoardStatus] = mapped_column(
        status_column(JobBoardStatus), default=JobBoardStatus.NOT_POSTED
    )
    job_board_post_url: Mapped[str | None] = mapped_column(String(500))
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class JobDescriptionStatus(StrEnum):
    """Where a JD draft is in the interviewer's approval."""

    DRAFT = "draft"
    APPROVED = "approved"
    REJECTED = "rejected"


class JobDescription(TimestampMixin, Base):
    """One JD draft. Each regeneration after feedback is a new version."""

    __tablename__ = "job_descriptions"
    __table_args__ = (UniqueConstraint("job_id", "version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[JobDescriptionStatus] = mapped_column(
        status_column(JobDescriptionStatus), default=JobDescriptionStatus.DRAFT
    )
    reviewer_feedback: Mapped[str | None] = mapped_column(Text)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
