"""Applicants for a job and their parsed CVs (F1).

Privacy (N20): no columns for age, gender, ethnicity, nationality, religion
or marital status. Deleting a candidate deletes all their data (N19),
because every child table uses ON DELETE CASCADE.
"""

from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, status_column


class CandidateStatus(StrEnum):
    RECEIVED = "received"  # CV file is in the intake folder
    PARSED = "parsed"
    PARSE_FAILED = "parse_failed"  # this CV failed; the rest of the batch goes on


class Candidate(TimestampMixin, Base):
    __tablename__ = "candidates"
    # The CV Collector skips a Drive file it has already fetched for this job.
    __table_args__ = (UniqueConstraint("job_id", "drive_file_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str | None] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(50))
    cv_filename: Mapped[str] = mapped_column(String(255))
    drive_file_id: Mapped[str | None] = mapped_column(String(200))
    # Education, work history, skills, certifications, projects.
    parsed_cv: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    status: Mapped[CandidateStatus] = mapped_column(
        status_column(CandidateStatus), default=CandidateStatus.RECEIVED
    )
    parse_error: Mapped[str | None] = mapped_column(Text)
