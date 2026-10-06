"""Hiring Assistant API: read a job's chat, send a message, review the JD.

Interviewers only (N9); the candidate never sees the assistant (§4B-10).
Every request runs the graph until it answers or pauses for review; the
thread is saved by the checkpointer, so nothing is lost on a restart (N26).
"""

import logging
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from langchain_core.messages import HumanMessage
from langgraph.errors import GraphRecursionError
from langgraph.types import Command
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant import posting
from app.assistant.schemas import JobDescriptionContent
from app.assistant.thread_view import thread_items
from app.auth.dependencies import require_interviewer
from app.db.database import get_db
from app.db.models import Job, JobDescription
from app.db.models.job import JobDescriptionStatus
from app.graphs.hiring_assistant import (
    build_hiring_assistant,
    posting_message,
    thread_config,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/assistant",
    tags=["hiring assistant"],
    dependencies=[Depends(require_interviewer)],
)

NOT_FOUND = "This job no longer exists."
REVIEW_FIRST = "Please approve, edit or reject the job description first."
NOTHING_TO_REVIEW = "There is no job description waiting for review."
APPROVE_FIRST = "Approve a job description before posting it."
STUCK = "The assistant couldn't finish this request. Please rephrase it or try again."


class MessageRequest(BaseModel):
    """A chat message from the interviewer."""

    text: str = Field(min_length=1, max_length=2000)


class ReviewRequest(BaseModel):
    """The interviewer's decision on the JD waiting for review (§4B-7)."""

    action: Literal["approve", "edit", "reject"]
    feedback: str | None = Field(default=None, max_length=1000)
    content: JobDescriptionContent | None = None  # the edited JD (for "edit")

    @model_validator(mode="after")
    def needs_details(self):
        """A rejection needs feedback; an edit needs the edited text."""
        if self.action == "reject" and not (self.feedback or "").strip():
            raise ValueError("Tell the assistant what to change.")
        if self.action == "edit" and self.content is None:
            raise ValueError("The edited job description is missing.")
        return self


class ThreadOut(BaseModel):
    """The chat as the screen shows it, plus the review waiting (if any)."""

    job_id: int
    items: list[dict]
    pending_review: dict | None


def _graph(request: Request):
    """The Hiring Assistant graph, using the app's database checkpointer."""
    return build_hiring_assistant(request.app.state.checkpointer)


def _require_job(db: Session, job_id: int) -> None:
    """Stop with 404 if the job does not exist."""
    if db.get(Job, job_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)


def _thread(graph, db: Session, job_id: int) -> ThreadOut:
    """Read the saved thread and any review the graph is waiting for."""
    snapshot = graph.get_state(thread_config(job_id))
    messages = snapshot.values.get("messages", []) if snapshot.values else []
    pending = next((i.value for task in snapshot.tasks for i in task.interrupts), None)
    return ThreadOut(
        job_id=job_id, items=thread_items(db, messages), pending_review=pending
    )


def _run(graph, graph_input, job_id: int) -> None:
    """Run one turn of the graph; a turn that never ends (the LLM keeps
    calling tools) is stopped by the step limit and gets a clear message."""
    try:
        graph.invoke(graph_input, thread_config(job_id))
    except GraphRecursionError:
        logger.warning("Assistant turn hit the step limit: job %d", job_id)
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, STUCK) from None


@router.get("/jobs/{job_id}/thread", response_model=ThreadOut)
def get_thread(
    job_id: int, request: Request, db: Annotated[Session, Depends(get_db)]
) -> ThreadOut:
    """Return a job's chat thread."""
    _require_job(db, job_id)
    return _thread(_graph(request), db, job_id)


@router.post("/jobs/{job_id}/messages", response_model=ThreadOut)
def send_message(
    job_id: int,
    body: MessageRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ThreadOut:
    """Send a chat message; the assistant answers (calling tools if needed)."""
    _require_job(db, job_id)
    graph = _graph(request)
    if _thread(graph, db, job_id).pending_review:
        raise HTTPException(status.HTTP_409_CONFLICT, REVIEW_FIRST)
    _run(graph, {"messages": [HumanMessage(body.text)], "job_id": job_id}, job_id)
    return _thread(graph, db, job_id)


@router.post("/jobs/{job_id}/review", response_model=ThreadOut)
def review_job_description(
    job_id: int,
    body: ReviewRequest,
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> ThreadOut:
    """Approve, edit or reject the JD; the paused graph continues from there."""
    _require_job(db, job_id)
    graph = _graph(request)
    if not _thread(graph, db, job_id).pending_review:
        raise HTTPException(status.HTTP_409_CONFLICT, NOTHING_TO_REVIEW)
    decision = body.model_dump(mode="json", exclude_none=True)
    _run(graph, Command(resume=decision), job_id)
    return _thread(graph, db, job_id)


@router.post("/jobs/{job_id}/retry", response_model=ThreadOut)
def retry_turn(
    job_id: int, request: Request, db: Annotated[Session, Depends(get_db)]
) -> ThreadOut:
    """Continue a chat turn that stopped because the AI failed. The message
    was already saved, so it is not sent again; the graph resumes from the
    step that failed."""
    _require_job(db, job_id)
    graph = _graph(request)
    snapshot = graph.get_state(thread_config(job_id))
    unfinished = bool(snapshot.next)
    if unfinished and not _thread(graph, db, job_id).pending_review:
        _run(graph, None, job_id)
    return _thread(graph, db, job_id)


@router.post("/jobs/{job_id}/post", response_model=ThreadOut)
def post_again(
    job_id: int, request: Request, db: Annotated[Session, Depends(get_db)]
) -> ThreadOut:
    """Post the approved JD to the job board again: after a failure, or once
    the application form link has been added. The result joins the chat."""
    _require_job(db, job_id)
    graph = _graph(request)
    if _thread(graph, db, job_id).pending_review:
        raise HTTPException(status.HTTP_409_CONFLICT, REVIEW_FIRST)
    approved = db.scalar(
        select(JobDescription.id).where(
            JobDescription.job_id == job_id,
            JobDescription.status == JobDescriptionStatus.APPROVED,
        )
    )
    if approved is None:
        raise HTTPException(status.HTTP_409_CONFLICT, APPROVE_FIRST)
    result = posting.post_job(job_id)
    graph.update_state(thread_config(job_id), {"messages": [posting_message(result)]})
    return _thread(graph, db, job_id)
