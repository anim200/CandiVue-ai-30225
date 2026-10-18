"""Post-interview API (F5, F6, F8-F10): the Q&A analysis of an ended
interview (with the CV claims check, interview score and interview quality),
its assessment report with the interviewer's review (HITL), the report as a
printable HTML file, the selection email after an approved report (§4B-14),
and the reports of a job for the Reports page and the side-by-side
comparison. Interviewers only (N9): candidates never see
analyses, scores or reports.

Both run in the background (LangGraphs 3 and 4): the analysis starts when
the interview ends, the report when the analysis finishes. The pages poll
these routes for progress; "Try again" continues a failed run where it
stopped.
"""

import logging
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.analysis.interview_quality import consistency
from app.analysis.report_html import render_report
from app.auth.dependencies import CurrentUser, require_interviewer
from app.core import clock
from app.db.database import get_db
from app.db.models import (
    AssessmentReport,
    Candidate,
    InterviewSession,
    Job,
    QAAnalysis,
    User,
)
from app.db.models.assessment import ReviewStatus
from app.db.models.interview import SessionStatus
from app.db.models.run import RunStatus
from app.graphs import final_assessment, qa_analysis
from app.interviews import emails

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api",
    tags=["interview analysis and reports"],
    dependencies=[Depends(require_interviewer)],
)

NOT_FOUND = "This interview no longer exists."
JOB_NOT_FOUND = "This job no longer exists."
NOT_ENDED = "The interview has not ended yet: the analysis starts when it ends."
ANALYSIS_RUNNING = "The Q&A analysis is already running."
NO_ANALYSIS = "The Q&A analysis must finish before the report can be prepared."
REPORT_RUNNING = "The report is already being prepared."
NO_REPORT = "There is no report for this interview yet."
NOT_IN_REVIEW = "This report is not waiting for your review."
NOT_APPROVED = "The selection email can be sent once the report is approved."
ALREADY_SELECTED = "The selection email was already sent to this candidate."
NO_EMAIL = "This candidate has no email address."
ACTIVE = (RunStatus.PENDING, RunStatus.RUNNING)


class RunOut(BaseModel):
    """A background run's status (progress: Q&A units evaluated, of how many)."""

    status: RunStatus
    error: str | None
    processed: int | None = None
    total: int | None = None
    started_at: datetime | None
    finished_at: datetime | None


class AnalysisOut(BaseModel):
    """The interview's Q&A analysis: its run and, when done, the results
    (Q&A units with evaluations, requirement coverage, unexplored ones, CV
    claims, interview score, interview quality with the comparison to the
    job's other interviews)."""

    run: RunOut | None
    results: dict[str, Any] | None


class StartIn(BaseModel):
    """again=true: analyse (or write the report) afresh, replacing the
    current one; otherwise start it, or continue a failed one."""

    again: bool = False


class ReportOut(BaseModel):
    """The assessment report: generation status, review status and content."""

    id: int
    status: RunStatus
    error: str | None
    review_status: ReviewStatus
    content: dict[str, Any]
    reviewer_feedback: str | None
    reviewed_by: str | None
    approved_at: datetime | None
    created_at: datetime


class ReportPageOut(BaseModel):
    """What the report page needs: the analysis it rests on and the report."""

    analysis: RunOut | None
    report: ReportOut | None
    selected_at: datetime | None = None  # when the selection email was sent


class ReviewIn(BaseModel):
    """The interviewer's decision; a change request needs a comment."""

    action: Literal["approve", "request_changes"]
    feedback: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def comment_for_changes(self) -> "ReviewIn":
        """ "What should change?" is required when asking for changes."""
        self.feedback = (self.feedback or "").strip() or None
        if self.action == "request_changes" and not self.feedback:
            raise ValueError("Say what should change.")
        return self


class SelectionEmailOut(BaseModel):
    """The selection email to check before sending: recipient, subject, text
    and the template it was made from."""

    to: str
    subject: str
    text: str
    template: str


class SelectionEmailIn(BaseModel):
    """The checked (possibly edited) selection email."""

    subject: str = Field(min_length=2, max_length=200)
    text: str = Field(min_length=10, max_length=5000)


class JobReportOut(BaseModel):
    """One ended interview of a job and its report, for the Reports list and
    the comparison (report: None while not prepared)."""

    interview_id: int
    candidate_id: int
    candidate_name: str
    interview_at: datetime
    analysis_status: RunStatus | None
    report: ReportOut | None


# ---------- Q&A analysis (F5) ----------


@router.get("/interviews/{interview_id}/analysis", response_model=AnalysisOut)
def get_analysis(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> AnalysisOut:
    """The interview's Q&A analysis: progress while it runs, results after."""
    session = _session(db, interview_id)
    analysis = _analysis(db, interview_id)
    return AnalysisOut(
        run=_run(analysis) if analysis else None,
        results=_with_consistency(db, session, analysis.results) if analysis else None,
    )


@router.post("/interviews/{interview_id}/analysis", response_model=AnalysisOut)
def start_analysis(
    interview_id: int, body: StartIn, db: Annotated[Session, Depends(get_db)]
) -> AnalysisOut:
    """Start the analysis of an ended interview, continue a failed one, or
    (again) analyse it afresh; the report is then prepared afresh too."""
    session = _session(db, interview_id)
    if session.status != SessionStatus.ENDED:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_ENDED)
    current = _analysis(db, interview_id)
    if current is not None and current.status in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, ANALYSIS_RUNNING)
    qa_analysis.start_analysis(db, interview_id, again=body.again)
    return get_analysis(interview_id, db)


# ---------- assessment report (F6) ----------


@router.get("/interviews/{interview_id}/report", response_model=ReportPageOut)
def get_report(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> ReportPageOut:
    """The interview's report and the analysis it rests on."""
    session = _session(db, interview_id)
    analysis = _analysis(db, interview_id)
    report = final_assessment.latest_report(db, interview_id)
    return ReportPageOut(
        analysis=_run(analysis) if analysis else None,
        report=_report(db, report) if report else None,
        selected_at=db.get(Candidate, session.candidate_id).selected_at,
    )


@router.post("/interviews/{interview_id}/report", response_model=ReportPageOut)
def start_report(
    interview_id: int, body: StartIn, db: Annotated[Session, Depends(get_db)]
) -> ReportPageOut:
    """Prepare the report, continue a failed one, or (again) write it afresh."""
    _session(db, interview_id)
    current = final_assessment.latest_report(db, interview_id)
    if current is not None and current.status in ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, REPORT_RUNNING)
    if final_assessment.start_report(db, interview_id, again=body.again) is None:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_ANALYSIS)
    return get_report(interview_id, db)


@router.post("/interviews/{interview_id}/report/review", response_model=ReportPageOut)
def review_report(
    interview_id: int,
    body: ReviewIn,
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_interviewer)],
) -> ReportPageOut:
    """Approve the report (it becomes final) or request changes with a
    comment (the next version is written with it, then reviewed again)."""
    _session(db, interview_id)
    report = final_assessment.latest_report(db, interview_id)
    if (
        report is None
        or report.status != RunStatus.WAITING_FOR_REVIEW
        or report.review_status != ReviewStatus.PENDING_REVIEW
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_IN_REVIEW)
    approve = body.action == "approve"
    final_assessment.submit_review(db, report, approve, body.feedback, user.id)
    logger.info(
        "Report %s: report %d",
        "approved" if approve else "changes requested",
        report.id,
    )
    return get_report(interview_id, db)


@router.get("/interviews/{interview_id}/report/export", response_class=Response)
def export_report(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """The report as a printable HTML file (drafts are marked as such)."""
    session = _session(db, interview_id)
    report = final_assessment.latest_report(db, interview_id)
    if report is None or not report.content:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NO_REPORT)
    approved = report.review_status == ReviewStatus.APPROVED
    reviewer = db.get(User, report.reviewed_by_id) if report.reviewed_by_id else None
    html = render_report(
        report.content,
        candidate=_candidate_name(db, session),
        job_title=db.get(Job, session.job_id).title,
        interview_at=session.started_at or session.scheduled_at,
        duration_minutes=_minutes(session),
        approved_by=reviewer.full_name if approved and reviewer else None,
        approved_at=report.approved_at if approved else None,
    )
    return Response(
        html,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="assessment-report-{interview_id}.html"',
            "Cache-Control": "no-store",
        },
    )


# ---------- selection email (§4B-14) ----------


@router.get(
    "/interviews/{interview_id}/selection-email", response_model=SelectionEmailOut
)
def preview_selection_email(
    interview_id: int, db: Annotated[Session, Depends(get_db)]
) -> SelectionEmailOut:
    """The selection email from the knowledge-base template (or the
    standard text), to check and edit before sending."""
    session = _session(db, interview_id)
    candidate = _selectable(db, session)
    email = emails.selection_email(db, candidate, db.get(Job, session.job_id))
    return SelectionEmailOut(to=candidate.email, **email)


@router.post("/interviews/{interview_id}/selection-email", response_model=ReportPageOut)
def send_selection_email(
    interview_id: int, body: SelectionEmailIn, db: Annotated[Session, Depends(get_db)]
) -> ReportPageOut:
    """Send the checked selection email; the candidate is then marked as
    selected and is never emailed twice."""
    session = _session(db, interview_id)
    candidate = _selectable(db, session, lock=True)
    problem = emails.deliver_selection(candidate.email, body.subject, body.text)
    if problem:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, problem)
    candidate.selected_at = clock.now()
    db.commit()
    logger.info("Selection email sent: candidate %d", candidate.id)
    return get_report(interview_id, db)


@router.get("/jobs/{job_id}/reports", response_model=list[JobReportOut])
def job_reports(
    job_id: int, db: Annotated[Session, Depends(get_db)]
) -> list[JobReportOut]:
    """Every ended interview of the job with its report, newest first."""
    if db.get(Job, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, JOB_NOT_FOUND)
    sessions = db.scalars(
        select(InterviewSession)
        .where(
            InterviewSession.job_id == job_id,
            InterviewSession.status == SessionStatus.ENDED,
        )
        .order_by(
            InterviewSession.ended_at.desc().nulls_last(), InterviewSession.id.desc()
        )
    )
    rows = []
    for session in sessions:
        analysis = _analysis(db, session.id)
        report = final_assessment.latest_report(db, session.id)
        rows.append(
            JobReportOut(
                interview_id=session.id,
                candidate_id=session.candidate_id,
                candidate_name=_candidate_name(db, session),
                interview_at=session.started_at or session.scheduled_at,
                analysis_status=analysis.status if analysis else None,
                report=_report(db, report) if report else None,
            )
        )
    return rows


# ---------- helpers ----------


def _session(db: Session, interview_id: int) -> InterviewSession:
    """The interview, or 404."""
    session = db.get(InterviewSession, interview_id)
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return session


def _selectable(
    db: Session, session: InterviewSession, lock: bool = False
) -> Candidate:
    """The candidate, if they may get the selection email: the report is
    approved, they were not emailed yet and have an address; or 409. lock:
    hold the row, so two clicks cannot send it twice."""
    report = final_assessment.latest_report(db, session.id)
    if report is None or report.review_status != ReviewStatus.APPROVED:
        raise HTTPException(status.HTTP_409_CONFLICT, NOT_APPROVED)
    candidate = db.get(Candidate, session.candidate_id, with_for_update=lock)
    if candidate.selected_at:
        raise HTTPException(status.HTTP_409_CONFLICT, ALREADY_SELECTED)
    if not candidate.email:
        raise HTTPException(status.HTTP_409_CONFLICT, NO_EMAIL)
    return candidate


def _analysis(db: Session, interview_id: int) -> QAAnalysis | None:
    """The interview's Q&A analysis, if any."""
    return db.scalar(select(QAAnalysis).where(QAAnalysis.session_id == interview_id))


def _with_consistency(
    db: Session, session: InterviewSession, results: dict | None
) -> dict | None:
    """The results with the interview quality compared to the job's other
    analysed interviews (worked out now, so it uses the latest ones)."""
    if not results or not results.get("quality"):
        return results
    others = db.scalars(
        select(QAAnalysis.results)
        .join(InterviewSession, InterviewSession.id == QAAnalysis.session_id)
        .where(
            InterviewSession.job_id == session.job_id,
            InterviewSession.id != session.id,
            QAAnalysis.results.is_not(None),
        )
    ).all()
    quality = results["quality"] | {"consistency": consistency(results, list(others))}
    return results | {"quality": quality}


def _run(analysis: QAAnalysis) -> RunOut:
    """The analysis run as the pages show it."""
    return RunOut(
        status=analysis.status,
        error=analysis.error,
        processed=min(analysis.processed, analysis.total or analysis.processed),
        total=analysis.total,
        started_at=analysis.started_at,
        finished_at=analysis.finished_at,
    )


def _report(db: Session, report: AssessmentReport) -> ReportOut:
    """A report as the pages show it."""
    reviewer = db.get(User, report.reviewed_by_id) if report.reviewed_by_id else None
    return ReportOut(
        id=report.id,
        status=report.status,
        error=report.error,
        review_status=report.review_status,
        content=report.content or {},
        reviewer_feedback=report.reviewer_feedback,
        reviewed_by=reviewer.full_name if reviewer else None,
        approved_at=report.approved_at,
        created_at=report.created_at,
    )


def _candidate_name(db: Session, session: InterviewSession) -> str:
    """The candidate's name (or the CV file name when none was found)."""
    candidate = db.get(Candidate, session.candidate_id)
    return candidate.full_name or candidate.cv_filename


def _minutes(session: InterviewSession) -> int | None:
    """How long the interview lasted, in whole minutes."""
    if session.started_at and session.ended_at:
        return max(
            round((session.ended_at - session.started_at).total_seconds() / 60), 1
        )
    return None
