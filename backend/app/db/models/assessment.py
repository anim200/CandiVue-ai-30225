"""Q&A analysis and the final assessment report (F5, F6 — LangGraphs 3, 4)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, status_column
from app.db.models.run import RunStateMixin


class QAAnalysis(RunStateMixin, TimestampMixin, Base):
    """Q&A pairs, their evaluations and requirement coverage for one interview."""

    __tablename__ = "qa_analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), unique=True
    )
    processed: Mapped[int] = mapped_column(default=0)  # Q&A units evaluated
    total: Mapped[int | None]  # Q&A units found (known after segmenting)
    results: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class ReviewStatus(StrEnum):
    """Where a report is in the interviewer's review."""

    PENDING_REVIEW = "pending_review"
    CHANGES_REQUESTED = "changes_requested"
    APPROVED = "approved"


class AssessmentReport(RunStateMixin, TimestampMixin, Base):
    """Consolidated report. The interviewer must approve it (HITL).

    `status` tracks the AI generating the report; `review_status` tracks the
    interviewer's decision about it.
    """

    __tablename__ = "assessment_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    session_id: Mapped[int] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), index=True
    )
    # Component scores, strengths, weaknesses, gaps, evidence links.
    content: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    review_status: Mapped[ReviewStatus] = mapped_column(
        status_column(ReviewStatus), default=ReviewStatus.PENDING_REVIEW
    )
    reviewer_feedback: Mapped[str | None] = mapped_column(Text)
    reviewed_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
