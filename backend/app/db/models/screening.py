"""CV screening runs and their results (F1, F2 — LangGraph 2)."""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, status_column


class RunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ScreeningRun(TimestampMixin, Base):
    """One press of "Screen CVs" for a job."""

    __tablename__ = "screening_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    status: Mapped[RunStatus] = mapped_column(
        status_column(RunStatus), default=RunStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)  # safe message, no stack trace


class CandidateScore(TimestampMixin, Base):
    """Result for one candidate in one screening run."""

    __tablename__ = "candidate_scores"
    __table_args__ = (UniqueConstraint("screening_run_id", "candidate_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    screening_run_id: Mapped[int] = mapped_column(
        ForeignKey("screening_runs.id", ondelete="CASCADE"), index=True
    )
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    # False = failed a must-have: excluded from the ranking.
    passed_gate: Mapped[bool]
    # Per requirement: met / partially met / unmet, with evidence.
    requirement_matches: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list
    )
    # Per dimension: score 0-100, weight and reason.
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    overall_score: Mapped[float | None] = mapped_column(Float)  # 0-100
    rank: Mapped[int | None]  # 1 = best; empty when excluded
    summary: Mapped[str | None] = mapped_column(Text)
