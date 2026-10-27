"""Talent rediscovery (F11, innovation): applicants of other jobs who agreed
to be considered for other vacancies, screened against one job. Kept apart
from screening runs, so they never mix with the job's own ranking."""

from typing import Any

from sqlalchemy import Float, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin
from app.db.models.run import RunStateMixin


class RediscoveryRun(RunStateMixin, TimestampMixin, Base):
    """One check of the talent pool for a job."""

    __tablename__ = "rediscovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    processed: Mapped[int] = mapped_column(default=0)  # past applicants checked
    total: Mapped[int | None]  # past applicants in the pool


class RediscoveryMatch(TimestampMixin, Base):
    """A past applicant who passes the job's mandatory requirements, with
    the same scores and evidence a screening gives."""

    __tablename__ = "rediscovery_matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("rediscovery_runs.id", ondelete="CASCADE"), index=True
    )
    # The original application (in another job). Deleting it deletes the match.
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    overall_score: Mapped[float] = mapped_column(Float)  # 0-100
    dimension_scores: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    requirement_matches: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list
    )
    summary: Mapped[str | None] = mapped_column(Text)
