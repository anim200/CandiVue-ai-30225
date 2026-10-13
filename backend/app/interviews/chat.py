"""Chat between the interviewer and the candidate during the interview.

Plain text only (the pages never render it as HTML), at most MAX_LENGTH
characters, and at most RATE_LIMIT messages per minute from each side. A
message is saved first and then pushed to the call (room.push_message), so
a reload or a dropped connection never loses one. Only while the interview
is scheduled or live; the candidate only after being let in.
"""

import logging
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import InterviewMessage, InterviewSession
from app.db.models.interview import Speaker
from app.interviews import room

logger = logging.getLogger(__name__)

MAX_LENGTH = 1000
RATE_LIMIT = 20  # messages per minute from one side
HISTORY_LIMIT = 500


class ChatError(Exception):
    """The message was not sent (the text is safe to show)."""


def as_dict(message: InterviewMessage) -> dict:
    """A message as the pages show it."""
    return {
        "id": message.id,
        "sender": message.sender.value,
        "text": message.text,
        "sent_at": message.created_at.isoformat(),
    }


def history(db: Session, session_id: int, after_id: int = 0) -> list[dict]:
    """The interview's messages (oldest first), only those after `after_id`."""
    rows = db.scalars(
        select(InterviewMessage)
        .where(
            InterviewMessage.session_id == session_id, InterviewMessage.id > after_id
        )
        .order_by(InterviewMessage.id)
        .limit(HISTORY_LIMIT)
    )
    return [as_dict(row) for row in rows]


def send(db: Session, session: InterviewSession, sender: Speaker, text: str) -> dict:
    """Check, save and push one message; returns it. Raises ChatError."""
    # Control characters (except new lines and tabs) are dropped.
    text = "".join(c for c in text if c.isprintable() or c in "\n\t").strip()
    if not text:
        raise ChatError("Type a message first.")
    if len(text) > MAX_LENGTH:
        raise ChatError(f"A message can have at most {MAX_LENGTH} characters.")
    recent = db.scalar(
        select(func.count(InterviewMessage.id)).where(
            InterviewMessage.session_id == session.id,
            InterviewMessage.sender == sender,
            InterviewMessage.created_at > clock.now() - timedelta(minutes=1),
        )
    )
    if recent >= RATE_LIMIT:
        raise ChatError("You are sending messages too fast. Wait a moment.")
    message = InterviewMessage(session_id=session.id, sender=sender, text=text)
    db.add(message)
    db.commit()
    db.refresh(message)  # created_at comes from the database
    saved = as_dict(message)
    room.push_message(session.id, saved)
    logger.info("Chat message: session %d, %s", session.id, sender.value)
    return saved
