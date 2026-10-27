"""Checks against the real, migrated database (run inside Docker)."""

from datetime import datetime, timezone

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.db.base import Base, include_name
from app.db.database import engine
from app.db.models import (
    AssessmentReport,
    Candidate,
    CandidateScore,
    InterviewSession,
    Job,
    QAAnalysis,
    ScreeningRun,
    TranscriptTurn,
)
from app.db.models.interview import Speaker

pytestmark = pytest.mark.usefixtures("database_available")


@pytest.fixture
def session():
    """A session whose changes are rolled back, so tests leave no data behind."""
    with engine.connect() as connection:
        transaction = connection.begin()
        with Session(bind=connection, join_transaction_mode="create_savepoint") as db:
            yield db
        transaction.rollback()


def test_migrations_created_every_table():
    existing = set(inspect(engine).get_table_names())
    assert set(Base.metadata.tables) <= existing


def test_migrations_match_models_and_keep_checkpoints():
    """No forgotten migration, and Alembic leaves LangGraph's tables alone."""
    with engine.connect() as connection:
        context = MigrationContext.configure(
            connection, opts={"include_name": include_name}
        )
        assert compare_metadata(context, Base.metadata) == []


def test_deleting_a_candidate_deletes_all_their_data(session):
    # Synthetic data only.
    job = Job(title="Test Job")
    session.add(job)
    session.flush()

    candidate = Candidate(
        job_id=job.id, full_name="Test Candidate", cv_filename="test.pdf"
    )
    run = ScreeningRun(job_id=job.id)
    session.add_all([candidate, run])
    session.flush()

    interview = InterviewSession(
        candidate_id=candidate.id,
        job_id=job.id,
        scheduled_at=datetime(2026, 10, 15, 10, 0, tzinfo=timezone.utc),
        join_token_hash="0" * 64,
    )
    session.add_all(
        [
            CandidateScore(
                screening_run_id=run.id, candidate_id=candidate.id, passed_gate=True
            ),
            interview,
        ]
    )
    session.flush()

    session.add_all(
        [
            TranscriptTurn(
                session_id=interview.id,
                speaker=Speaker.CANDIDATE,
                text="Test answer",
                start_ms=0,
                end_ms=1000,
            ),
            QAAnalysis(session_id=interview.id),
            AssessmentReport(candidate_id=candidate.id, session_id=interview.id),
        ]
    )
    session.flush()

    candidate_id, interview_id = candidate.id, interview.id
    session.delete(candidate)
    session.flush()
    session.expire_all()

    leftovers = {
        CandidateScore: CandidateScore.candidate_id == candidate_id,
        InterviewSession: InterviewSession.id == interview_id,
        TranscriptTurn: TranscriptTurn.session_id == interview_id,
        QAAnalysis: QAAnalysis.session_id == interview_id,
        AssessmentReport: AssessmentReport.candidate_id == candidate_id,
    }
    for model, condition in leftovers.items():
        count = session.scalar(select(func.count()).select_from(model).where(condition))
        assert count == 0, model.__tablename__
    # The job and the screening run are not candidate data and stay.
    assert session.get(Job, job.id) is not None
    assert session.get(ScreeningRun, run.id) is not None
