"""Jobs API: create a job (it starts a Hiring Assistant thread), list jobs,
and a job's applicants: the CVs the CV Collector received from the Google
Form, or the interviewer uploaded by hand (fallback); view and remove them.

Interviewers only (N9). Job profiles are filled in through the Hiring
Assistant chat (§4B-8), not through a form.
"""

import logging
import re
from datetime import datetime
from typing import Annotated, Any

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_interviewer
from app.collector.intake import CvRejected, check_cv, find_cv, remove_cv, save_cv
from app.core import clock
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import (
    Candidate,
    CandidateScore,
    InterviewSession,
    Job,
    JobDescription,
    ScreeningRun,
)
from app.db.models.candidate import CandidateStatus
from app.db.models.job import JobBoardStatus, JobDescriptionStatus, JobStatus
from app.db.models.run import RunStatus
from app.interviews import planning
from app.knowledge.files import clean_filename
from app.runs.cleanup import purge_stale_threads
from app.screening.weights import ScoringWeights, effective_weights

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/jobs", tags=["jobs"], dependencies=[Depends(require_interviewer)]
)

NOT_FOUND = "This job no longer exists."
APPLICANT_NOT_FOUND = "This applicant no longer exists."
FILE_MISSING = "This CV file is not available."
# Browsers show PDFs; Word files are downloaded.
CV_MEDIA_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
NEW_JOB_TITLE = "New job"
CLOSED = (
    "Applications closed on {when}. To add CVs, change the closing date in the chat."
)


class JobOut(BaseModel):
    """A job as shown in the jobs list and the assistant's thread list."""

    id: int
    title: str
    status: JobStatus
    profile: dict[str, Any] | None
    stage: str  # drafting_profile, jd_to_approve, jd_approved, posted, ...
    google_form_url: str | None = None
    job_board_post_url: str | None = None
    cvs_received: int = 0  # usable CVs collected (rejected files not counted)
    # The weights screening will use, with "source": interviewer / ai / default.
    weights: dict[str, Any]
    ai_weights: dict[str, Any] | None = None  # the AI suggestion, if any
    applications_close_at: datetime | None = None  # CVs after it are not taken
    # The latest screening run: its status, when it finished and how many
    # passed the gate (ranked) or not (excluded).
    screening_status: RunStatus | None = None
    screened_at: datetime | None = None
    ranked_count: int = 0
    excluded_count: int = 0
    shortlisted_count: int = 0
    interview_count: int = 0  # scheduled (or live) interviews
    updated_at: datetime


class CvOut(BaseModel):
    """A CV the collector received for a job (no scores: those come later)."""

    id: int
    full_name: str | None
    email: str | None
    cv_filename: str
    status: CandidateStatus
    problem: str | None  # why it was rejected or could not be read
    # "form" (Google Form, via the collector), "upload" (by hand) or
    # "rediscovered" (added from another job's talent pool, F11).
    source: str
    received_at: datetime
    open_to_other_roles: bool  # in the talent pool (the applicant agreed)
    rediscovered_from: str | None  # the job they first applied for


class UploadResult(BaseModel):
    """What happened to one uploaded file."""

    filename: str
    added: bool
    message: str  # "Added" or why the file was refused


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


def gate_count(db: Session, run_id: int, passed: bool) -> int:
    """How many candidates passed (or did not pass) the gate in a run."""
    return db.scalar(
        select(func.count(CandidateScore.id)).where(
            CandidateScore.screening_run_id == run_id,
            CandidateScore.passed_gate.is_(passed),
        )
    )


def to_job_out(db: Session, job: Job) -> JobOut:
    """Build the job's summary with its current stage."""
    latest = db.scalar(
        select(JobDescription)
        .where(JobDescription.job_id == job.id)
        .order_by(JobDescription.version.desc())
        .limit(1)
    )
    run = db.scalar(
        select(ScreeningRun)
        .where(ScreeningRun.job_id == job.id)
        .order_by(ScreeningRun.id.desc())
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
        cvs_received=db.scalar(
            select(func.count(Candidate.id)).where(
                Candidate.job_id == job.id,
                Candidate.status != CandidateStatus.REJECTED,
            )
        ),
        weights=effective_weights(job),
        ai_weights=job.ai_weights,
        applications_close_at=job.applications_close_at,
        screening_status=run.status if run else None,
        screened_at=run.finished_at if run else None,
        ranked_count=gate_count(db, run.id, True) if run else 0,
        excluded_count=gate_count(db, run.id, False) if run else 0,
        shortlisted_count=db.scalar(
            select(func.count(Candidate.id)).where(
                Candidate.job_id == job.id, Candidate.shortlisted_at.is_not(None)
            )
        ),
        interview_count=db.scalar(
            select(func.count(InterviewSession.id)).where(
                InterviewSession.job_id == job.id,
                InterviewSession.status.in_(planning.ACTIVE),
            )
        ),
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


@router.get("/{job_id}/cvs", response_model=list[CvOut])
def list_cvs(job_id: int, db: Annotated[Session, Depends(get_db)]) -> list[CvOut]:
    """The CVs received for a job, newest first, with their status."""
    if db.get(Job, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    candidates = db.scalars(
        select(Candidate)
        .where(Candidate.job_id == job_id)
        .order_by(Candidate.created_at.desc())
    ).all()
    origins = dict(
        db.execute(
            select(Candidate.id, Job.title)
            .join(Job, Job.id == Candidate.job_id)
            .where(Candidate.id.in_([c.rediscovered_from_id for c in candidates]))
        ).all()
    )
    return [cv_out(c, origins.get(c.rediscovered_from_id)) for c in candidates]


def cv_out(candidate: Candidate, origin_job: str | None = None) -> CvOut:
    """One applicant as the job page shows it."""
    if candidate.rediscovered_from_id:
        source = "rediscovered"
    else:
        source = "form" if candidate.drive_file_id else "upload"
    return CvOut(
        id=candidate.id,
        full_name=candidate.full_name,
        email=candidate.email,
        cv_filename=candidate.cv_filename,
        status=candidate.status,
        problem=candidate.parse_error,
        source=source,
        received_at=candidate.created_at,
        open_to_other_roles=candidate.open_to_other_roles,
        rediscovered_from=origin_job,
    )


MAX_FILES_PER_UPLOAD = 30
NOT_A_NAME = {"cv", "resume", "curriculum", "vitae", "final", "updated", "new"}


def name_from_filename(filename: str) -> str | None:
    """A first guess at the applicant's name from the file name, e.g.
    "02-alex_rowan-CV.pdf" -> "Alex Rowan" (parsing the CV replaces it later)."""
    stem = filename.rsplit(".", 1)[0]
    words = re.sub(r"[^A-Za-z]+", " ", stem).split()  # letters only
    words = [word for word in words if word.lower() not in NOT_A_NAME]
    return " ".join(word.capitalize() for word in words)[:200] or None


@router.post("/{job_id}/cvs", response_model=list[UploadResult])
def upload_cvs(
    job_id: int,
    db: Annotated[Session, Depends(get_db)],
    files: Annotated[list[UploadFile], File()],
    open_to_other_roles: Annotated[bool, Form()] = False,
) -> list[UploadResult]:
    """Add CVs by hand (fallback when the Google Form route is not available).
    Same checks as the collector, and none after the closing date; each file
    gets its own result, and one refused file does not stop the others.
    open_to_other_roles: the interviewer confirms these applicants agreed to
    be considered for other vacancies (talent pool, F11; off by default)."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if job.applications_close_at and job.applications_close_at <= clock.now():
        closed = clock.local_text(job.applications_close_at)
        raise HTTPException(status.HTTP_409_CONFLICT, CLOSED.format(when=closed))
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            f"Upload at most {MAX_FILES_PER_UPLOAD} CVs at a time.",
        )
    max_bytes = get_settings().max_cv_mb * 1024 * 1024
    results = []
    for upload in files:
        filename = clean_filename(upload.filename or "")
        data = upload.file.read(max_bytes + 1)  # one byte more detects "too big"
        try:
            file_type = check_cv(data, filename)
        except CvRejected as exc:
            results.append(
                UploadResult(filename=filename, added=False, message=str(exc))
            )
            continue
        candidate = Candidate(
            job_id=job_id,
            full_name=name_from_filename(filename),
            cv_filename=filename,
            open_to_other_roles=open_to_other_roles,
        )
        db.add(candidate)
        db.flush()  # the candidate's id names the file
        save_cv(job_id, candidate.id, file_type, data)
        db.commit()
        results.append(UploadResult(filename=filename, added=True, message="Added"))
    logger.info(
        "CVs uploaded for job %d: %d added, %d refused",
        job_id,
        sum(r.added for r in results),
        sum(not r.added for r in results),
    )
    return results


@router.put("/{job_id}/weights", response_model=JobOut)
def set_weights(
    job_id: int, body: ScoringWeights, db: Annotated[Session, Depends(get_db)]
) -> JobOut:
    """Save the interviewer's scoring weights; they win over the AI suggestion."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    job.weights = body.model_dump(mode="json")
    db.commit()
    logger.info("Scoring weights set by the interviewer: job %d", job_id)
    return to_job_out(db, job)


@router.delete("/{job_id}/weights", response_model=JobOut)
def reset_weights(job_id: int, db: Annotated[Session, Depends(get_db)]) -> JobOut:
    """Forget the interviewer's weights: the AI suggestion (or the defaults)
    applies again."""
    job = db.get(Job, job_id)
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    job.weights = None
    db.commit()
    return to_job_out(db, job)


def _applicant(db: Session, job_id: int, candidate_id: int) -> Candidate:
    """The applicant if they belong to this job; 404 otherwise."""
    candidate = db.get(Candidate, candidate_id)
    if candidate is None or candidate.job_id != job_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, APPLICANT_NOT_FOUND)
    return candidate


@router.get("/{job_id}/cvs/{candidate_id}/file")
def get_cv_file(
    job_id: int, candidate_id: int, db: Annotated[Session, Depends(get_db)]
) -> FileResponse:
    """The applicant's CV file from the intake folder (PDF opens in the
    browser, Word downloads). Not stored by the browser (no-store)."""
    candidate = _applicant(db, job_id, candidate_id)
    path = find_cv(job_id, candidate.id)
    if path is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, FILE_MISSING)
    return FileResponse(
        path,
        media_type=CV_MEDIA_TYPES[path.suffix],
        filename=candidate.cv_filename or path.name,
        content_disposition_type="inline" if path.suffix == ".pdf" else "attachment",
        headers={"Cache-Control": "no-store"},
    )


@router.delete("/{job_id}/cvs/{candidate_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_applicant(
    job_id: int, candidate_id: int, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """Remove an applicant and everything about them (N19): the database
    rows (scores, interviews, transcripts, analyses, reports, face
    reference: they cascade), the CV file and the saved workflow state."""
    candidate = _applicant(db, job_id, candidate_id)
    db.delete(candidate)
    db.commit()
    remove_cv(job_id, candidate_id)
    purge_stale_threads(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
