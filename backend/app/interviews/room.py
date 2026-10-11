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
"""

import asyncio
import logging
from datetime import timedelta

from livekit import api
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import InterviewSession
from app.db.models.interview import SessionStatus

logger = logging.getLogger(__name__)

TICKET_HOURS = 4  # long enough for an interview with reconnects
NOT_SET_UP = "Video calls are not set up yet: add LIVEKIT_API_SECRET to .env."


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
