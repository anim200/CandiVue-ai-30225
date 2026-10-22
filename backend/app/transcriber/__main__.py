"""Start the transcriber: "python -m app.transcriber" (the transcriber container).

Every POLL_SECONDS it looks for live interviews with the interviewer or the
candidate in the call and starts one RoomListener for each (F4). A
listener that stops (interview ended, room left empty, connection lost) is started again
on a later round if the interview is still live, so a restart or a dropped
connection only loses a few seconds; turns already saved stay (N26).
Without DEEPGRAM_API_KEY it only tells each live room "not set up".
When Docker stops or restarts it (SIGTERM), every listener first saves its
last words, then it exits.
"""

import asyncio
import contextlib
import logging
import signal

from sqlalchemy import select

from app.core import clock
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.db.database import SessionLocal
from app.db.models import InterviewSession
from app.db.models.interview import SessionStatus
from app.transcriber.listener import (
    NOT_SET_UP,
    RoomListener,
    humans_in_room,
    set_problem,
)

logger = logging.getLogger("app.transcriber")

POLL_SECONDS = 2  # how soon a new call is joined (the first words count)


def live_sessions() -> list[tuple[int, object]]:
    """(id, start time) of every live interview."""
    with SessionLocal() as db:
        rows = db.execute(
            select(InterviewSession.id, InterviewSession.started_at).where(
                InterviewSession.status == SessionStatus.LIVE
            )
        )
        return [(row.id, row.started_at) for row in rows]


Listeners = dict[int, tuple[RoomListener, asyncio.Task]]


async def one_round(listeners: Listeners) -> None:
    """Start listeners for live interviews that need one; forget finished ones."""
    settings = get_settings()
    for session_id, (_listener, task) in list(listeners.items()):
        if task.done():
            listeners.pop(session_id)
            if not task.cancelled() and task.exception():
                logger.warning(
                    "Listener stopped (%s): session %d",
                    type(task.exception()).__name__,
                    session_id,
                )
    for session_id, started_at in await asyncio.to_thread(live_sessions):
        if settings.deepgram_api_key is None:
            await asyncio.to_thread(set_problem, session_id, NOT_SET_UP)
            continue
        if session_id in listeners or not await humans_in_room(session_id):
            continue
        listener = RoomListener(session_id, started_at or clock.now())
        listeners[session_id] = (listener, asyncio.create_task(listener.run()))


async def run() -> None:
    """Rounds forever; a failed round (e.g. the database restarting) is
    logged and tried again."""
    settings = get_settings()
    setup_logging(settings.log_level)
    if settings.livekit_api_secret is None:
        logger.warning("Video calls are not set up (LIVEKIT_API_SECRET): idle.")
    elif settings.deepgram_api_key is None:
        logger.warning(NOT_SET_UP)
    logger.info("Transcriber started: checking every %d s", POLL_SECONDS)
    stopping = asyncio.Event()
    loop = asyncio.get_running_loop()
    for stop_signal in (signal.SIGTERM, signal.SIGINT):
        with contextlib.suppress(NotImplementedError):  # e.g. on Windows
            loop.add_signal_handler(stop_signal, stopping.set)
    listeners: Listeners = {}
    while not stopping.is_set():
        if settings.livekit_api_secret is not None:
            try:
                await one_round(listeners)
            except Exception as error:  # noqa: BLE001 - try again next round
                logger.warning("Transcriber round failed: %s", type(error).__name__)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stopping.wait(), POLL_SECONDS)
    # Stopping: every listener saves its last words before the exit.
    logger.info("Transcriber stopping: saving the last words")
    for listener, _task in listeners.values():
        await listener.leave()
    tasks = [task for _listener, task in listeners.values()]
    if tasks:
        await asyncio.wait(tasks, timeout=12)  # Compose waits 15 s (stop_grace_period)


if __name__ == "__main__":
    asyncio.run(run())
