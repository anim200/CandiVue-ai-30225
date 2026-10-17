"""Deleting a candidate and all associated data (N19), and saved workflow
state that is no longer needed (N16): with the real database and
checkpointer. Synthetic data only."""

from datetime import timedelta
from typing import TypedDict

import pytest
from langgraph.graph import END, START, StateGraph
from sqlalchemy import select, text

from app.auth.security import Role, create_access_token
from app.collector import intake
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import (
    Candidate,
    CandidateScore,
    FaceReference,
    InterviewSession,
    Job,
    QAAnalysis,
    ScreeningRun,
    TranscriptTurn,
)
from app.db.models.interview import InvitationStatus, SessionStatus, Speaker
from app.db.models.run import RunStatus
from app.graphs.checkpointer import open_checkpointer
from app.interviews import planning
from app.runs.cleanup import purge_stale_threads

pytestmark = pytest.mark.usefixtures("database_available")


class Note(TypedDict):
    """The state of a one-step graph used to save a thread."""

    text: str


def save_thread(thread_id: str) -> None:
    """Save some graph state under this thread id, as a real run would."""
    graph = StateGraph(Note)
    graph.add_node("step", lambda state: {"text": state["text"] + "."})
    graph.add_edge(START, "step")
    graph.add_edge("step", END)
    with open_checkpointer() as checkpointer:
        compiled = graph.compile(checkpointer=checkpointer)
        compiled.invoke({"text": "CV text"}, {"configurable": {"thread_id": thread_id}})


def threads() -> set[str]:
    """Every saved thread id."""
    with SessionLocal() as db:
        return set(db.scalars(text("SELECT DISTINCT thread_id FROM checkpoints")))


@pytest.fixture
def applicant(tmp_path, monkeypatch):
    """A screened applicant with a CV file, an ended interview with a
    transcript, a failed analysis, a face reference and saved threads."""
    monkeypatch.setattr(get_settings(), "cv_intake_dir", str(tmp_path))
    with SessionLocal() as db:
        job = Job(title="Privacy test job")
        db.add(job)
        db.flush()
        candidate = Candidate(
            job_id=job.id, full_name="Pat Sample", cv_filename="cv.pdf"
        )
        db.add(candidate)
        db.flush()
        intake.save_cv(job.id, candidate.id, "pdf", b"%PDF-1.4 synthetic")
        run = ScreeningRun(job_id=job.id, status=RunStatus.COMPLETED)
        db.add(run)
        db.flush()
        db.add(
            CandidateScore(
                screening_run_id=run.id, candidate_id=candidate.id, passed_gate=True
            )
        )
        session = InterviewSession(
            candidate_id=candidate.id,
            job_id=job.id,
            scheduled_at=clock.now() - timedelta(hours=1),
            join_token_hash=planning.new_link_token()[1],
            invitation_status=InvitationStatus.SENT,
            status=SessionStatus.ENDED,
        )
        db.add(session)
        db.flush()
        db.add(
            TranscriptTurn(
                session_id=session.id,
                speaker=Speaker.CANDIDATE,
                text="Hi",
                start_ms=0,
                end_ms=900,
            )
        )
        db.add(
            FaceReference(
                session_id=session.id, candidate_id=candidate.id, embedding=b"x"
            )
        )
        analysis = QAAnalysis(session_id=session.id, status=RunStatus.FAILED)
        db.add(analysis)
        db.commit()
        ids = {
            "job": job.id,
            "candidate": candidate.id,
            "session": session.id,
            "analysis": analysis.id,
            "run": run.id,
        }
    save_thread(f"qa_analysis-{ids['analysis']}")  # failed: kept to continue
    save_thread(f"assistant-interview-{ids['session']}")  # the room assistant's chat
    yield ids
    with SessionLocal() as db:
        if job := db.get(Job, ids["job"]):
            db.delete(job)
            db.commit()


def test_deleting_a_candidate_removes_everything_about_them(applicant, client):
    headers = {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}
    save_thread("unknown-kind-1")  # not ours to judge: never touched

    answer = client.delete(
        f"/api/jobs/{applicant['job']}/cvs/{applicant['candidate']}", headers=headers
    )

    assert answer.status_code == 204
    with SessionLocal() as db:
        assert db.get(Candidate, applicant["candidate"]) is None
        assert db.get(InterviewSession, applicant["session"]) is None
        assert db.get(QAAnalysis, applicant["analysis"]) is None
        for model in (CandidateScore, FaceReference):
            assert (
                db.scalar(
                    select(model.id).where(model.candidate_id == applicant["candidate"])
                )
                is None
            )
        assert (
            db.scalar(
                select(TranscriptTurn.id).where(
                    TranscriptTurn.session_id == applicant["session"]
                )
            )
            is None
        )
    assert intake.find_cv(applicant["job"], applicant["candidate"]) is None
    left = threads()
    assert f"qa_analysis-{applicant['analysis']}" not in left
    assert f"assistant-interview-{applicant['session']}" not in left
    assert "unknown-kind-1" in left
    with open_checkpointer() as checkpointer:
        checkpointer.delete_thread("unknown-kind-1")


def test_only_state_that_is_still_needed_is_kept(applicant):
    finished = f"cv_screening-{applicant['run']}"
    save_thread(finished)

    with SessionLocal() as db:
        purge_stale_threads(db)

    left = threads()
    assert finished not in left  # a finished run: nothing to continue
    assert f"qa_analysis-{applicant['analysis']}" in left  # failed: "Try again"
    assert f"assistant-interview-{applicant['session']}" in left  # the interview exists
