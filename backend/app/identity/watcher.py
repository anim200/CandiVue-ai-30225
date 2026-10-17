"""The live identity check (F7), run by the transcriber service while it is
in the call (it is hidden and cannot send video).

FaceWatcher looks at the candidate's camera every CHECK_SECONDS: it takes
the newest picture (in memory only, never saved, N16), compares the face
with the references (app/identity/references.py) and decides with the
last few pictures (app/identity/matching.py). Each result is saved on the
interview and pushed to the interviewer only (data channel topic
"identity"; the page also asks the backend, so nothing depends on the
push). "Check again" from the interviewer starts with fresh pictures. A
candidate without consent is never checked.
"""

import asyncio
import contextlib
import logging

import numpy as np
from livekit import rtc

from app.core import clock
from app.db.database import SessionLocal
from app.db.models import InterviewSession
from app.identity.faces import FaceError, face_embedding, similarity
from app.identity.matching import WINDOW, Sample, decide
from app.identity.references import is_set_up, job_references

logger = logging.getLogger(__name__)

TOPIC = "identity"
CHECK_SECONDS = 5
NO_PICTURE_SECONDS = 10  # no frame for this long: the camera is off


class FaceWatcher:
    """Checks one candidate camera until it is stopped."""

    def __init__(self, session_id: int, started_at, track, publication, push):
        self.session_id = session_id
        self.started_at = started_at
        self.track = track
        self.publication = publication
        self.push = push  # (message, reliable, topic) → sends to the interviewer
        self.stopped = asyncio.Event()

    async def run(self) -> None:
        """Check until stopped. A failure is logged and the call goes on
        without the check (the panel keeps the last result)."""
        try:
            await self._check_until_stopped()
        except Exception as error:  # noqa: BLE001 - never stop the call or the transcript
            logger.warning(
                "Identity check stopped: session %d (%s)",
                self.session_id,
                type(error).__name__,
            )

    async def _check_until_stopped(self) -> None:
        """Compare a picture every CHECK_SECONDS and report each result."""
        if not is_set_up():
            return
        references, recheck_seen = await asyncio.to_thread(_load, self.session_id)
        if references is None:
            return  # no consent: the face is never checked
        # The full-size picture: a smaller layer (e.g. 320x240 from a 640x480
        # camera) leaves too few pixels for a face (measured in the 45-minute
        # test: "no face" after LiveKit switched layers). Same machine, so
        # the bandwidth does not matter.
        self.publication.set_video_quality(rtc.VideoQuality.VIDEO_QUALITY_HIGH)
        stream = rtc.VideoStream(self.track, capacity=1)  # keeps the newest only
        samples: list[Sample] = []
        logger.info("Identity check started: session %d", self.session_id)
        try:
            while not self.stopped.is_set():
                sample = await self._next_sample(stream, references)
                samples = [*samples[-(WINDOW - 1) :], sample]
                result = decide(samples)
                saved, recheck = await asyncio.to_thread(
                    _save_result, self.session_id, result, self.started_at, recheck_seen
                )
                if recheck != recheck_seen:  # "Check again": start afresh
                    recheck_seen, samples = recheck, []
                    continue
                await self.push({"kind": "identity", "identity": saved}, True, TOPIC)
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.stopped.wait(), CHECK_SECONDS)
        finally:
            await stream.aclose()

    async def stop(self) -> None:
        """Stop checking (the camera left or the call ended)."""
        self.stopped.set()

    async def _next_sample(self, stream, references: dict) -> Sample:
        """The newest picture compared with the references."""
        try:
            event = await asyncio.wait_for(anext(aiter(stream)), NO_PICTURE_SECONDS)
        except (TimeoutError, StopAsyncIteration):
            return Sample(problem="camera_off")
        frame = event.frame.convert(rtc.VideoBufferType.RGB24)
        pixels = np.frombuffer(frame.data, np.uint8).reshape(
            frame.height, frame.width, 3
        )
        return await asyncio.to_thread(compare, pixels[:, :, ::-1].copy(), references)


def compare(image: np.ndarray, references: dict) -> Sample:
    """One picture (BGR) compared with the invited candidate's reference
    and with the job's other applicants."""
    try:
        face = face_embedding(image)
    except FaceError as exc:
        return Sample(problem=exc.reason)
    own = max(similarity(face, ref) for ref in references["own"])
    others = [(name, similarity(face, ref)) for name, ref in references["others"]]
    return Sample(own=own, other=max(others, key=lambda o: o[1], default=None))


def _load(session_id: int) -> tuple[dict | None, object]:
    """The references to compare with (None: no consent) and when the
    interviewer last asked to check again."""
    with SessionLocal() as db:
        session = db.get(InterviewSession, session_id)
        return job_references(db, session), session.identity_recheck_at


def _save_result(session_id: int, result: dict, started_at, recheck_seen):
    """Save the latest result (with the first time the identity was
    confirmed) unless the interviewer asked to check again since: then
    nothing is saved and the request time is returned to start afresh.
    Returns (the saved result, the latest request time)."""
    with SessionLocal() as db:
        session = db.get(InterviewSession, session_id)
        if session.identity_recheck_at != recheck_seen:
            return None, session.identity_recheck_at
        previous = session.identity_result or {}
        confirmed = previous.get("confirmed_at_ms")
        if result["state"] == "matched" and confirmed is None:
            confirmed = int((clock.now() - started_at).total_seconds() * 1000)
        saved = result | {
            "checked_at": clock.now().isoformat(),
            "confirmed_at_ms": confirmed,
        }
        session.identity_result = saved
        db.commit()
        return saved, recheck_seen
