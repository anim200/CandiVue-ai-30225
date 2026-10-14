"""From Deepgram's pieces of speech to transcript turns (F4).

A turn is what one speaker says until they pause. Pieces of the same turn
are joined; the turn is saved as soon as its first piece arrives and
updated with every next piece, so the interviewer sees a long answer grow
(near real time) and nothing is lost if the connection drops.

A new turn starts after a real pause: PAUSE_SECONDS or more between the
last word and the next (from Deepgram's word times), or Deepgram's
UtteranceEnd. Deepgram's own sentence ends (speech_final) do not split a
turn: on a choppy connection they can come after almost every word. A
very long turn (MAX_TURN_SECONDS) and the end of the stream close it too.

Times are milliseconds from the start of the interview (started_at):
to_ms turns Deepgram's times (seconds from the first audio of one
connection) into them, using when each piece of audio was heard (see
listener.Timeline).
"""

from collections.abc import Callable
from dataclasses import dataclass

from app.db.database import SessionLocal
from app.db.models import TranscriptTurn
from app.db.models.interview import Speaker
from app.transcriber.deepgram import Segment, UtteranceEnd

PAUSE_SECONDS = 1.2  # a pause this long between words starts a new turn
MAX_TURN_SECONDS = 45  # a very long answer is split into several turns


@dataclass
class TurnState:
    """The turn being written: what to save (row_id: None until saved)."""

    text: str
    start_ms: int
    end_ms: int
    row_id: int | None = None


class TurnBuilder:
    """Joins the pieces of one speaker's stream into turns. feed() returns
    the turn to save (new or changed), or None."""

    def __init__(self, to_ms: Callable[[float], int]):
        self.to_ms = to_ms
        self.current: TurnState | None = None
        self._start_s = 0.0
        self._end_s = 0.0

    def feed(self, event: Segment | UtteranceEnd) -> TurnState | None:
        """Take one piece (or a pause) and return the turn to save."""
        if isinstance(event, UtteranceEnd):
            self.close()
            return None
        if not event.text:
            return None
        if self.current is not None and event.start - self._end_s >= PAUSE_SECONDS:
            self.close()  # a real pause since the last word
        if self.current is None:
            self._start_s = event.start
            self.current = TurnState(
                text=event.text,
                start_ms=self.to_ms(event.start),
                end_ms=self.to_ms(event.end),
            )
        else:
            self.current.text = f"{self.current.text} {event.text}"
            self.current.end_ms = self.to_ms(event.end)
        self._end_s = event.end
        changed = self.current
        if event.end - self._start_s >= MAX_TURN_SECONDS:
            self.close()
        return changed

    def close(self) -> None:
        """The speaker paused: the next piece starts a new turn."""
        self.current = None


def save_turn(session_id: int, speaker: Speaker, turn: TurnState) -> int:
    """Insert the turn, or update it when it has grown; returns its row id."""
    with SessionLocal() as db:
        row = db.get(TranscriptTurn, turn.row_id) if turn.row_id else None
        if row is None:
            row = TranscriptTurn(session_id=session_id, speaker=speaker)
            db.add(row)
        row.text = turn.text
        row.start_ms = turn.start_ms
        row.end_ms = turn.end_ms
        db.commit()
        return row.id
