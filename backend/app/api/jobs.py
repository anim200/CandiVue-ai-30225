"""Jobs API: create a job (it starts a Hiring Assistant thread) and list jobs.

Interviewers only (N9). Job profiles are filled in through the Hiring
Assistant chat (§4B-8), not through a form.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_interviewer
from app.db.database import get_db
from app.db.models import Job, JobDescription
from app.db.models.job import JobBoardStatus, JobDescriptionStatus, JobStatus

router = APIRouter(
    prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_interviewer)]
)

NOT_FOUND = "This job no longer exists."
NEW_JOB_TITLE = "New job"


class JobOut(BaseModel):
    """A job as shown in the jobs list and the assistant's thread list."""

    id: int
    title: str
    status: JobStatus
    profile: dict[str, Any] | None
    stage: str  # drafting_profile, jd_to_approve, jd_approved, posted, ...
    google_form_url: str | None = None
    job_board_post_url: str | None = None
    updated_at: datetime


def job_stage(job: Job, latest_jd: JobDescription | None) -> str:
    """Describe how far the job has come, for the progress bar and lists."""
    if latest_jd is None:
        return "drafting_profile" if not job.profile else "profile_saved"
    if latest_jd.status == JobDescriptionStatus.APPROVED:
        if job.job_board_status == JobBoardStatus.POSTED:
            return "posted"
        if job.job_board_status == JobBoardStatus.FAILED:
            return "posting_failed"
        if job.job_board_status == JobBoardStatus.AWAITING_CONFIRMATION:
            return "post_to_confirm"
        return "jd_approved"
    if latest_jd.status == JobDescriptionStatus.DRAFT:
        return "jd_to_approve"
    return "jd_rejected"


def to_job_out(db: Session, job: Job) -> JobOut:
    """Build the job's summary with its current stage."""
    latest = db.scalar(
        select(JobDescription)
        .where(JobDescription.job_id == job.id)
        .order_by(JobDescription.version.desc())
        .limit(1)
    )
    return JobOut(
        id=job.id,
        title=job.title,
        status=job.status,
        profile=job.profile or None,
        stage=job_stage(job, latest),
        google_form_url=job.google_form_url,
        job_board_post_url=job.job_board_post_url,
        updated_at=max(job.updated_at, latest.updated_at) if latest else job.updated_at,
    )


@router.get("", response_model=list[JobOut])
def list_jobs(db: Annotated[Session, Depends(get_db)]) -> list[JobOut]:
    """List all jobs, most recently changed first."""
    jobs = [to_job_out(db, job) for job in db.scalars(select(Job))]
    return sorted(jobs, key=lambda job: job.updated_at, reverse=True)


@router.post("", response_model=JobOut, status_code=status.HTTP_201_CREATED)
def create_job(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_interviewer)],
) -> JobOut:
    """Create an empty job; the interviewer describes it in the assistant chat."""
    job = Job(title=NEW_JOB_TITLE, created_by_id=user.id)
    db.add(job)
    db.commit()
    db.refresh(job)
    return to_job_out(db, job)


@router.get("/{job_id}", response_model=JobOut)
def get_job(job_id: int, db: Annotated[Session, Depends(get_db)]) -> JobOut:
    """Return one job's summary."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return to_job_out(db, job)
