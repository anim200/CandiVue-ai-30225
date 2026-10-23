"""All tables. Importing this package registers them on Base.metadata,
which Alembic compares with the database."""

from app.db.models.assessment import AssessmentReport, QAAnalysis
from app.db.models.candidate import Candidate
from app.db.models.interview import (
    FaceReference,
    InterviewMessage,
    InterviewSession,
    TranscriptTurn,
)
from app.db.models.job import Job, JobDescription
from app.db.models.knowledge import KnowledgeChunk, KnowledgeDocument
from app.db.models.llm_model import LlmModel
from app.db.models.rediscovery import RediscoveryMatch, RediscoveryRun
from app.db.models.screening import CandidateScore, CvPassage, ScreeningRun
from app.db.models.user import User

__all__ = [
    "AssessmentReport",
    "Candidate",
    "CandidateScore",
    "CvPassage",
    "FaceReference",
    "InterviewMessage",
    "InterviewSession",
    "Job",
    "JobDescription",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "LlmModel",
    "QAAnalysis",
    "RediscoveryMatch",
    "RediscoveryRun",
    "ScreeningRun",
    "TranscriptTurn",
    "User",
]
