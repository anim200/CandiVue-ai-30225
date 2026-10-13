"""Video calls (F3) with LiveKit, a video server running in Docker.

Each interview has its own room, "interview-<session id>". The backend gives
each person a short-lived ticket (a LiveKit access token, signed with our
secret) for exactly that room, with their role in the identity:
"interviewer-<user id>" or "candidate-<session id>". LiveKit lets one
connection per identity, so a second tab (or a reload) replaces the first.
LiveKit tells us who joined through signed webhooks: the first join makes
the interview Live and saves its start time. End closes the room for
everyone. Video and audio go browser to LiveKit to browser; nothing is
recorded (N16).

Waiting room: the candidate gets a ticket only after the interviewer let
them in (admitted_at); once let in, a dropped connection or a reload goes
straight back in (F3). Each open page sends a heartbeat, so each side knows
whether the other is there.

Chat: messages are saved by the backend and then pushed to everyone in the
room by LiveKit (send_data, topic "chat"). Browsers cannot send data into
the room themselves (can_publish_data is off), so every message goes
through the backend's checks.
"""

import asyncio
import json
import logging
from datetime import datetime, timedelta

from livekit import api
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import InterviewSession
from app.db.models.interview import SessionStatus

logger = logging.getLogger(__name__)

TICKET_HOURS = 4  # long enough for an interview with reconnects
NOT_SET_UP = "Video calls are not set up yet: add LIVEKIT_API_SECRET to .env."
# A page that has not sent a heartbeat for this long has been closed.
PRESENCE_SECONDS = 15
CHAT_TOPIC = "chat"


class RoomError(Exception):
    """The call cannot be opened (the message is safe to show)."""


def room_name(session_id: int) -> str:
    """The LiveKit room of an interview."""
    return f"interview-{session_id}"


def ticket(session: InterviewSession, identity: str, name: str) -> str:
    """A ticket (signed token) to join this interview's room only."""
    key, secret = _keys()
    # Camera and microphone only: no data messages (least privilege).
    grants = api.VideoGrants(
        room_join=True, room=room_name(session.id), can_publish_data=False
    )
    return (
        api.AccessToken(key, secret)
        .with_identity(identity)
        .with_name(name)
        .with_grants(grants)
        .with_ttl(timedelta(hours=TICKET_HOURS))
        .to_jwt()
    )


def end_room(session_id: int) -> None:
    """Close the room: everyone still in it is disconnected. Never fails:
    the interview is ended or cancelled even if the room cannot be closed."""

    async def delete() -> None:
        """Ask LiveKit to delete the room."""
        key, secret = _keys()
        async with api.LiveKitAPI(get_settings().livekit_url, key, secret) as livekit:
            await livekit.room.delete_room(
                api.DeleteRoomRequest(room=room_name(session_id))
            )

    try:
        asyncio.run(delete())
    except Exception as exc:  # noqa: BLE001 - not set up, or the room is already gone
        logger.info("Room not closed (%s): session %d", type(exc).__name__, session_id)


def is_present(seen_at: datetime | None) -> bool:
    """True when a page sent its heartbeat within PRESENCE_SECONDS."""
    return seen_at is not None and clock.now() - seen_at < timedelta(
        seconds=PRESENCE_SECONDS
    )


def lobby(session: InterviewSession) -> dict:
    """The waiting room as both sides see it."""
    return {
        "interviewer_present": is_present(session.interviewer_seen_at),
        "candidate_waiting": session.admitted_at is None
        and is_present(session.candidate_waiting_at),
        "admitted": session.admitted_at is not None,
    }


def push_message(session_id: int, message: dict) -> None:
    """Send a saved chat message to everyone in the call at once. Never
    fails: if LiveKit cannot be reached, the pages still load it from the
    backend (they check every few seconds)."""

    async def send() -> None:
        """Ask LiveKit to deliver the message to the room."""
        key, secret = _keys()
        async with api.LiveKitAPI(get_settings().livekit_url, key, secret) as livekit:
            await livekit.room.send_data(
                api.SendDataRequest(
                    room=room_name(session_id),
                    data=json.dumps(message).encode(),
                    kind=api.DataPacket.Kind.RELIABLE,
                    topic=CHAT_TOPIC,
                )
            )

    try:
        asyncio.run(send())
    except Exception as exc:  # noqa: BLE001 - nobody in the call yet, or LiveKit down
        logger.info("Chat not pushed (%s): session %d", type(exc).__name__, session_id)


def handle_webhook(db: Session, body: str, authorization: str) -> None:
    """Record who joined, from LiveKit's signed webhook. A forged or
    altered message raises an error (it is signed with our secret)."""
    key, secret = _keys()
    event = api.WebhookReceiver(api.TokenVerifier(key, secret)).receive(
        body, authorization
    )
    if event.event != "participant_joined" or not event.room.name.startswith(
        "interview-"
    ):
        return
    session = db.get(InterviewSession, int(event.room.name.removeprefix("interview-")))
    if session is None:
        return
    role, _, person_id = event.participant.identity.partition("-")
    if role not in ("interviewer", "candidate"):
        return  # e.g. a future listen-only helper: not a participant
    if role == "interviewer":
        session.interviewer_id = int(person_id)  # who actually took part
    if session.status == SessionStatus.SCHEDULED:
        session.status = SessionStatus.LIVE
        session.started_at = clock.now()
    db.commit()
    logger.info("Joined the call: %s, session %d", role, session.id)


def _keys() -> tuple[str, str]:
    """The LiveKit key and secret, or RoomError when not set up."""
    settings = get_settings()
    if settings.livekit_api_secret is None:
        raise RoomError(NOT_SET_UP)
    return settings.livekit_api_key, settings.livekit_api_secret.get_secret_value()
