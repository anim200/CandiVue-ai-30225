"""The saved transcript as the analysis graphs read it (F4 → F5, F6).

Every turn becomes a numbered line, e.g. "L12 [02:47] Candidate: ...". The
LLM points to line numbers, never to free text, so each judgement stays
traceable to a timestamped transcript segment (F5, F6). Before a line is
sent to the LLM provider, the names of both people, email addresses, phone
numbers and links are removed (README, N18).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Candidate, InterviewSession, TranscriptTurn, User
from app.db.models.interview import Speaker
from app.interviews.cv_view import clean_text, name_parts


@dataclass(frozen=True)
class Line:
    """One transcript turn. number: L1, L2, ... in the order spoken; times
    are milliseconds from the start of the interview."""

    number: int
    turn_id: int
    speaker: Speaker
    text: str
    start_ms: int
    end_ms: int

    def as_prompt(self) -> str:
        """The line as the LLM reads it, e.g. "L12 [02:47] Candidate: ..."."""
        who = self.speaker.value.capitalize()
        return f"L{self.number} [{clock_text(self.start_ms)}] {who}: {self.text}"


def load_lines(db: Session, session: InterviewSession) -> list[Line]:
    """The interview's turns in order, numbered, with names and contact
    details removed."""
    candidate = db.get(Candidate, session.candidate_id)
    interviewer = (
        db.get(User, session.interviewer_id) if session.interviewer_id else None
    )
    names = name_parts(
        candidate.full_name, interviewer.full_name if interviewer else None
    )
    turns = db.scalars(
        select(TranscriptTurn)
        .where(TranscriptTurn.session_id == session.id)
        .order_by(TranscriptTurn.start_ms, TranscriptTurn.id)
    )
    return [
        Line(
            number=number,
            turn_id=turn.id,
            speaker=turn.speaker,
            text=clean_text(turn.text, names),
            start_ms=turn.start_ms,
            end_ms=turn.end_ms,
        )
        for number, turn in enumerate(turns, start=1)
    ]


def clock_text(ms: int) -> str:
    """Milliseconds from the start as people read them: "02:47" or "1:02:47"."""
    seconds = max(ms, 0) // 1000
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    return (
        f"{hours}:{minutes:02d}:{seconds:02d}"
        if hours
        else f"{minutes:02d}:{seconds:02d}"
    )
