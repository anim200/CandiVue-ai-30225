"""Applicants for a job and their parsed CVs (F1).

Privacy (N20): no columns for age, gender, ethnicity, nationality, religion
or marital status. Deleting a candidate deletes all their data (N19),
because every child table uses ON DELETE CASCADE.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, status_column


class CandidateStatus(StrEnum):
    """How far a candidate's CV has been processed."""

    RECEIVED = "received"  # CV file is in the intake folder
    REJECTED = "rejected"  # wrong type or too large: not saved (reason kept)
    PARSED = "parsed"
    PARSE_FAILED = "parse_failed"  # this CV failed; the rest of the batch goes on


class Candidate(TimestampMixin, Base):
    """One applicant for a job, with their parsed CV."""

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
    # Set when the interviewer shortlists the candidate in the Hiring
    # Assistant; only shortlisted candidates can be invited to an interview.
    shortlisted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Set when the selection email was sent after the approved report
    # (§4B-14): the candidate was selected, and is not emailed twice.
    selected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Talent pool (F11): the applicant agreed (form question, or the
    # interviewer when adding the CV by hand) that this application may be
    # matched against other open vacancies. Never matched without it.
    open_to_other_roles: Mapped[bool] = mapped_column(
        default=False, server_default="false"
    )
    # Identity check (F7, §4B-15): the face photo sent with the form (its
    # Google Drive file) and the separate consent to use it. Processed only
    # once the applicant is invited (ApplicationPhoto).
    photo_file_id: Mapped[str | None] = mapped_column(String(200))
    photo_consent: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Set when this application was added from another job's talent pool
    # (the original application stays as it was).
    rediscovered_from_id: Mapped[int | None] = mapped_column(
        ForeignKey("candidates.id", ondelete="SET NULL")
    )
