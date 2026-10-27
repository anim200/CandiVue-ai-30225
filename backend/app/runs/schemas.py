"""What the API returns when the frontend asks "how far is this run?"."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.run import RunStatus


class RunStatusOut(BaseModel):
    """Status only: no scores, rankings or report content (N9)."""

    model_config = ConfigDict(from_attributes=True)  # build from a table row

    id: int
    status: RunStatus
    processed: int | None = None  # only screening runs count items
    total: int | None = None
    error: str | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
