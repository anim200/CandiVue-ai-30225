"""The job's latest screening results, as the shortlist and invitations use
them, and whether they are still up to date."""

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Candidate, CandidateScore, Job, ScreeningRun
from app.db.models.candidate import CandidateStatus
from app.db.models.run import RunStatus
from app.screening.weights import DIMENSIONS, effective_weights

NOT_SCREENED = "The CVs are not screened yet: click Screen CVs on the job page first."
NOT_FINISHED = (
    "The latest screening has not finished (or it stopped): wait or screen again."
)


@dataclass
class Row:
    """One CV's result in the latest screening run."""

    candidate: Candidate
    score: CandidateScore

    @property
    def name(self) -> str:
        """The candidate's name (or the file name when none was found)."""
        return self.candidate.full_name or self.candidate.cv_filename

    @property
    def ranked(self) -> bool:
        """True when the CV passed every mandatory requirement."""
        return self.score.passed_gate

    def label(self) -> str:
        """e.g. "rank 1 · Candidate H (86)"."""
        return f"rank {self.score.rank} · {self.name} ({self.score.overall_score:.0f})"


def latest_rows(db: Session, job: Job) -> tuple[ScreeningRun, list[Row]]:
    """The latest finished run and its results, ranked ones first (best first).
    Raises ValueError when there is no finished screening to use."""
    run = db.scalar(
        select(ScreeningRun)
        .where(ScreeningRun.job_id == job.id)
        .order_by(ScreeningRun.id.desc())
        .limit(1)
    )
    if run is None:
        raise ValueError(NOT_SCREENED)
    if run.status != RunStatus.COMPLETED:
        raise ValueError(NOT_FINISHED)
    rows = [
        Row(candidate, score)
        for score, candidate in db.execute(
            select(CandidateScore, Candidate)
            .join(Candidate, Candidate.id == CandidateScore.candidate_id)
            .where(CandidateScore.screening_run_id == run.id)
        )
    ]
    rows.sort(key=lambda row: (not row.ranked, row.score.rank or 0, row.candidate.id))
    return run, rows


def new_cv_count(db: Session, job: Job, run: ScreeningRun) -> int:
    """CVs that arrived after the run started (so they are not in its ranking)."""
    return db.scalar(
        select(func.count(Candidate.id)).where(
            Candidate.job_id == job.id,
            Candidate.status != CandidateStatus.REJECTED,
            Candidate.created_at > run.created_at,
        )
    )


def weights_changed(job: Job, run: ScreeningRun) -> bool:
    """True when the job's weights differ from the ones the run used."""
    current = effective_weights(job)
    return any(current[d] != run.weights.get(d) for d in DIMENSIONS)


def warnings(db: Session, job: Job, run: ScreeningRun) -> list[str]:
    """Why the ranking may not be final (shown, but nothing is blocked)."""
    notes = []
    if new := new_cv_count(db, job, run):
        notes.append(f"{new} new CV(s) arrived after the last screening.")
    if weights_changed(job, run):
        notes.append("The scoring weights changed after the last screening.")
    closes = job.applications_close_at
    if not closes or closes > clock.now():
        until = f" until {clock.local_text(closes)}" if closes else ""
        notes.append(f"Applications are still open{until}: more CVs may come.")
    return notes


def invitation_blockers(db: Session, job: Job, run: ScreeningRun) -> list[str]:
    """Why no invitation may be sent yet: every applicant must be screened
    first, so invitations wait for the close and a screening after it."""
    closes = job.applications_close_at
    if not closes:
        return ["Set when applications close first (set_application_deadline)."]
    if closes > clock.now():
        until = clock.local_text(closes)
        return [f"Applications are open until {until}: invite after they close."]
    problems = []
    if run.created_at < closes:
        problems.append(
            "The last screening ran before applications closed: screen the CVs again."
        )
    if new := new_cv_count(db, job, run):
        problems.append(
            f"{new} new CV(s) arrived after the last screening: screen again."
        )
    return problems
