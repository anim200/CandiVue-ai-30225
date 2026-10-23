"""Saved workflow state that is no longer needed (N16, N19).

LangGraph saves each run's state (checkpoints) so that a failed run can
continue where it stopped and a report can wait for the interviewer's
review. Once a run has finished, or its run, job or interview was deleted,
that state only holds copies of personal data (CV text, transcript lines,
chat messages). purge_stale_threads() deletes it: right after a candidate
is deleted, and every hour. A finished run also deletes its own state at
once (app/runs/runner.py).
"""

import logging

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.db.models import InterviewSession, Job
from app.db.models.run import RunStatus
from app.graphs.checkpointer import open_checkpointer
from app.runs.runner import RUN_KINDS

logger = logging.getLogger(__name__)

# The Hiring Assistant's chats: one per job and one per interview room.
CHATS = {"assistant-job": Job, "assistant-interview": InterviewSession}


def purge_stale_threads(db: Session) -> int:
    """Delete the saved state of finished runs and of deleted runs, jobs and
    interviews. Only known kinds of state are touched."""
    keep = set()
    for kind, run_kind in RUN_KINDS.items():
        model = run_kind.model
        unfinished = select(model.id).where(model.status != RunStatus.COMPLETED)
        keep |= {f"{kind}-{run_id}" for run_id in db.scalars(unfinished)}
    for kind, model in CHATS.items():
        keep |= {f"{kind}-{row_id}" for row_id in db.scalars(select(model.id))}
    known = set(RUN_KINDS) | set(CHATS)
    stale = [
        thread
        for thread in db.scalars(text("SELECT DISTINCT thread_id FROM checkpoints"))
        if thread.rsplit("-", 1)[0] in known and thread not in keep
    ]
    if stale:
        with open_checkpointer() as checkpointer:
            for thread in stale:
                checkpointer.delete_thread(thread)
        logger.info("Saved workflow state deleted: %d threads", len(stale))
    return len(stale)
