"""Dashboard API: the interviewer's home page (app/dashboard.py) in one
call. Read-only; interviewers only (N9)."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import dashboard
from app.auth.dependencies import require_interviewer
from app.db.database import get_db
from app.db.models.interview import InvitationStatus, SessionStatus

router = APIRouter(
    prefix="/api/dashboard",
    tags=["dashboard"],
    dependencies=[Depends(require_interviewer)],
)


class CountsOut(BaseModel):
    """The numbers on the home page's cards."""

    open_jobs: int
    applications_week: int  # usable CVs received in the last 7 days
    cvs_to_screen: int  # usable CVs of open jobs not in a screening yet
    interviews_today: int  # live now or scheduled for today
    reports_to_review: int
    selected_month: int  # selection emails sent this month


class StepOut(BaseModel):
    """One thing that needs the interviewer, with the page that does it."""

    kind: str  # live, interview, review, screen
    text: str
    detail: str
    action: str
    link: str


class UpcomingOut(BaseModel):
    """One of the next interviews."""

    id: int
    candidate_name: str
    job_title: str
    scheduled_at: datetime
    status: SessionStatus
    invitation_status: InvitationStatus


class DayOut(BaseModel):
    """Applications received on one local day."""

    day: str  # e.g. "2026-10-23"
    count: int


class DashboardOut(BaseModel):
    """Everything the home page shows."""

    counts: CountsOut
    next_steps: list[StepOut]
    upcoming: list[UpcomingOut]
    applications: list[DayOut]


@router.get("", response_model=DashboardOut)
def get_dashboard(db: Annotated[Session, Depends(get_db)]) -> DashboardOut:
    """What needs the interviewer now: counts, next steps, the next
    interviews and applications per day (last 14 days)."""
    return DashboardOut(**dashboard.summary(db))
