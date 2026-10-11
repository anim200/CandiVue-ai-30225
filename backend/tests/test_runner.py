"""Background runs: status, clear failures, progress and resume (N4, N6, N26).

A fake work function stands in for a LangGraph, so no AI is called.
Runs use the real database (inside Docker); the test job and its runs are
deleted at the end.
"""

import pytest

from app.ai.errors import AIServiceError
from app.db.database import SessionLocal
from app.db.models import Job, ScreeningRun
from app.db.models.run import RunStatus
from app.runs import runner
from app.runs.schemas import RunStatusOut

pytestmark = pytest.mark.usefixtures("database_available")

KIND = "test-screening"


@pytest.fixture
def job_id():
    """A synthetic job; deleting it also deletes its runs (cascade)."""
    with SessionLocal() as db:
        job = Job(title="Test Job")
        db.add(job)
        db.commit()
        job_id = job.id
    yield job_id
    with SessionLocal() as db:
        db.delete(db.get(Job, job_id))
        db.commit()
    runner.RUN_KINDS.pop(KIND, None)


def new_run(job_id: int, status: RunStatus = RunStatus.PENDING) -> int:
    """Create a screening run row with the given status and return its id."""
    with SessionLocal() as db:
        run = ScreeningRun(job_id=job_id, status=status)
        db.add(run)
        db.commit()
        return run.id


def load(run_id: int) -> ScreeningRun:
    """Read a screening run back from the database."""
    with SessionLocal() as db:
        return db.get(ScreeningRun, run_id)


def run_with(work, job_id: int) -> ScreeningRun:
    """Register a fake work function, run it in the background and wait."""
    runner.register_run_kind(KIND, ScreeningRun, work)
    run_id = new_run(job_id)
    runner.start_run(KIND, run_id).result()  # wait for the background thread
    return load(run_id)


def test_successful_run_is_completed(job_id):
    run = run_with(lambda run_id: None, job_id)

    assert run.status == RunStatus.COMPLETED
    assert run.started_at is not None and run.finished_at is not None
    assert run.error is None


def test_ai_failure_gives_clear_message(job_id):
    def work(run_id):
        """Fake work function for this test."""
        raise AIServiceError("The AI service is unavailable.")

    run = run_with(work, job_id)

    assert run.status == RunStatus.FAILED
    assert run.error == runner.AI_FAILURE_MESSAGE


def test_unexpected_error_hides_technical_details(job_id):
    def work(run_id):
        """Fake work function for this test."""
        raise ValueError("secret internal detail")

    run = run_with(work, job_id)

    assert run.status == RunStatus.FAILED
    assert run.error == runner.UNEXPECTED_FAILURE_MESSAGE
    assert "secret" not in run.error


def test_pause_for_review_is_not_completed(job_id):
    run = run_with(lambda run_id: RunStatus.WAITING_FOR_REVIEW, job_id)

    assert run.status == RunStatus.WAITING_FOR_REVIEW
    assert run.finished_at is None


def test_progress_is_kept_when_a_run_fails(job_id):
    def work(run_id):
        """Fake work function for this test."""
        runner.save_progress(ScreeningRun, run_id, processed=12, total=20)
        raise AIServiceError("The AI service is unavailable.")

    run = run_with(work, job_id)

    assert (run.processed, run.total) == (12, 20)


def test_interrupted_runs_resume_at_startup(job_id):
    resumed = []
    runner.register_run_kind(KIND, ScreeningRun, resumed.append)
    interrupted = new_run(job_id, RunStatus.RUNNING)
    waiting = new_run(job_id, RunStatus.WAITING_FOR_REVIEW)
    done = new_run(job_id, RunStatus.COMPLETED)

    for future in runner.resume_interrupted_runs():
        future.result()

    assert interrupted in resumed
    assert waiting not in resumed and done not in resumed
    assert load(interrupted).status == RunStatus.COMPLETED


def test_status_response_has_no_scores(job_id):
    run = run_with(lambda run_id: None, job_id)

    body = RunStatusOut.model_validate(run).model_dump()

    assert body["status"] == "completed"
    assert not {"score", "rank", "overall_score"} & set(body)


def test_graph_config_uses_a_fixed_thread_id():
    assert runner.graph_config("screening", 5) == {
        "configurable": {"thread_id": "screening-5"}
    }
