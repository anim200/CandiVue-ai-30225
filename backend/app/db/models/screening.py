"""CV screening runs and their results (F1, F2 — LangGraph 2), and the CV
passages with their embeddings used for semantic matching (vector store)."""

from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.db.base import Base, TimestampMixin
from app.db.models.run import RunStateMixin


class ScreeningRun(RunStateMixin, TimestampMixin, Base):
    """One press of "Screen CVs" for a job."""

    __tablename__ = "screening_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    # Progress shown in the UI, e.g. "12 of 20 CVs" (N25).
    processed: Mapped[int] = mapped_column(default=0)
    total: Mapped[int | None]
    # The weights this run used and who set them, so a ranking can always be
    # explained and repeated (F2), even after the weights are changed.
    weights: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)


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


class CvPassage(Base):
    """One sentence or line of a candidate's CV and its embedding. Made once
    per CV and reused by later screening runs (the CV does not change)."""

    __tablename__ = "cv_passages"

    id: Mapped[int] = mapped_column(primary_key=True)
    candidate_id: Mapped[int] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]
    section: Mapped[str] = mapped_column(String(30))  # experience, skills, ...
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
