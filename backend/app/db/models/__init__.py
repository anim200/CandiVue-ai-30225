"""All tables. Importing this package registers them on Base.metadata,
which Alembic compares with the database."""

from app.db.models.assessment import AssessmentReport, QAAnalysis
from app.db.models.candidate import Candidate
from app.db.models.interview import InterviewSession, TranscriptTurn
from app.db.models.job import Job, JobDescription
from app.db.models.screening import CandidateScore, ScreeningRun
from app.db.models.user import User

__all__ = [
    "AssessmentReport",
    "Candidate",
    "CandidateScore",
    "InterviewSession",
    "Job",
    "JobDescription",
    "QAAnalysis",
    "ScreeningRun",
    "TranscriptTurn",
    "User",
]
