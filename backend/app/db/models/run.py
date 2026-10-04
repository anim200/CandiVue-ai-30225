"""Status columns shared by every long AI run (N4, N6, N26).

Used by screening runs (LangGraph 2), Q&A analyses (LangGraph 3) and
assessment reports (LangGraph 4). The background runner in app/runs fills
them in; the frontend reads them to show progress or a clear error.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import status_column


class RunStatus(StrEnum):
    PENDING = "pending"  # created, not started yet
    RUNNING = "running"
    WAITING_FOR_REVIEW = "waiting_for_review"  # paused for the interviewer (HITL)
    COMPLETED = "completed"
    FAILED = "failed"


class RunStateMixin:
    status: Mapped[RunStatus] = mapped_column(
        status_column(RunStatus), default=RunStatus.PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)  # safe message, no stack trace
