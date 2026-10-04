"""Runs long AI work in the background and records its status (N4, N6, N26).

How it works:
1. A feature registers its kind of run once, e.g. "screening" with its table
   and its work function (the LangGraph).
2. The API creates a run row, calls start_run() and answers at once.
3. A worker thread runs the work and sets the status: running, then
   completed, waiting_for_review or failed (with a safe message).
4. When the backend starts, resume_interrupted_runs() starts every run that
   was still pending or running when the backend stopped. The work uses
   graph_config(), so LangGraph continues from its last saved step.
"""

import logging
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select

from app.ai.llm import AIServiceError
from app.db.database import SessionLocal
from app.db.models.run import RunStatus

logger = logging.getLogger(__name__)

# Messages users see (N25): plain language, no technical details (N12).
AI_FAILURE_MESSAGE = "The AI service was unavailable. Please try again later."
UNEXPECTED_FAILURE_MESSAGE = "Something went wrong while processing. Please try again."

# Two workers: e.g. a CV batch and an interview analysis at the same time (N5).
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="run")


@dataclass
class RunKind:
    model: type  # a table with RunStateMixin columns
    # Does the work for one run id. Returns WAITING_FOR_REVIEW when the graph
    # paused for the interviewer; returns None when finished.
    work: Callable[[int], RunStatus | None]


RUN_KINDS: dict[str, RunKind] = {}


def register_run_kind(name: str, model: type, work: Callable) -> None:
    RUN_KINDS[name] = RunKind(model=model, work=work)


def graph_config(kind: str, run_id: int) -> dict:
    """LangGraph config for a run. The same thread_id after a restart means
    the graph continues from its last checkpoint instead of starting over."""
    return {"configurable": {"thread_id": f"{kind}-{run_id}"}}


def start_run(kind: str, run_id: int) -> Future:
    """Start the work in the background and return immediately."""
    return _executor.submit(execute_run, kind, run_id)


def execute_run(kind: str, run_id: int) -> None:
    """Run the work and record the outcome; errors from the work never escape."""
    run_kind = RUN_KINDS[kind]
    _update(run_kind.model, run_id, status=RunStatus.RUNNING,
            started_at=_now(), finished_at=None, error=None)
    logger.info("Run started: %s %d", kind, run_id)

    try:
        result = run_kind.work(run_id)
    except AIServiceError:
        # invoke_llm() already logged the cause.
        _fail(run_kind.model, run_id, AI_FAILURE_MESSAGE)
        logger.warning("Run failed (AI service): %s %d", kind, run_id)
        return
    except Exception:
        _fail(run_kind.model, run_id, UNEXPECTED_FAILURE_MESSAGE)
        logger.exception("Run failed (unexpected error): %s %d", kind, run_id)
        return

    if result == RunStatus.WAITING_FOR_REVIEW:
        _update(run_kind.model, run_id, status=RunStatus.WAITING_FOR_REVIEW)
        logger.info("Run waiting for review: %s %d", kind, run_id)
    else:
        _update(run_kind.model, run_id, status=RunStatus.COMPLETED,
                finished_at=_now())
        logger.info("Run completed: %s %d", kind, run_id)


def save_progress(model: type, run_id: int, processed: int, total: int) -> None:
    """Called by the work after each item (e.g. each CV), so the UI can show
    "12 of 20" and finished items are not lost on a restart (N25, N26)."""
    _update(model, run_id, processed=processed, total=total)


def resume_interrupted_runs() -> list[Future]:
    """Start again every run that was pending or running when the backend
    stopped. Runs waiting for the interviewer are left alone."""
    futures = []
    for kind, run_kind in RUN_KINDS.items():
        model = run_kind.model
        with SessionLocal() as db:
            run_ids = db.scalars(
                select(model.id).where(
                    model.status.in_([RunStatus.PENDING, RunStatus.RUNNING])
                )
            ).all()
        for run_id in run_ids:
            logger.info("Resuming interrupted run: %s %d", kind, run_id)
            futures.append(start_run(kind, run_id))
    return futures


def _fail(model: type, run_id: int, message: str) -> None:
    _update(model, run_id, status=RunStatus.FAILED, error=message,
            finished_at=_now())


def _update(model: type, run_id: int, **values) -> None:
    """Save the given column values on one run, in its own transaction."""
    with SessionLocal() as db:
        run = db.get(model, run_id)
        for column, value in values.items():
            setattr(run, column, value)
        db.commit()


def _now() -> datetime:
    return datetime.now(timezone.utc)
