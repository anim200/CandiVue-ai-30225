"""Listening to one live interview and writing its transcript (F4).

RoomListener joins the interview's LiveKit room as a hidden participant
("transcriber": it cannot send audio or video, and the people in the call do
not see it). For every person's microphone it starts a SpeakerStream; the
speaker is known from whose track it is (interviewer or candidate), so no
guessing from mixed audio is needed (F4, trainer clarification).

SpeakerStream sends that person's audio to Deepgram (50 ms pieces) and
saves the turns (TurnBuilder). Audio stays in memory only (N16). The text is
also pushed straight to the interviewer's page over the call's data
channel, addressed to the interviewer only (never to the candidate, N9):
words still being recognised ("interim") appear while they are spoken, and
every saved turn at once; the page also asks the backend every few seconds,
so nothing depends on the push.

No speech is lost on a slow or unreliable network: every audio piece is
taken from LiveKit at once and kept ("waiting") until a final result from
Deepgram covers it. A connection that stops answering is noticed within
about PING_TIMEOUT_SECONDS; the next connection sends the waiting audio
first, so the words come back late but complete, and nothing is repeated
(audio Deepgram has finished is never sent again). Turn times come from
when each piece was heard (Timeline), so they stay right after a muted
microphone or a reconnect.

Edge cases:
- Deepgram drops or cannot be reached: reconnect with a growing pause; the
  open turn is closed and the transcript continues where Deepgram left off.
  Up to MAX_WAITING_SECONDS of audio waits meanwhile (after that the oldest
  is dropped, with a warning in the log). A refused key or an empty account
  stops it with a clear problem shown in the room.
- A muted microphone sends no audio: KeepAlive keeps the stream open.
- A person reconnects: their old track ends (its last words are saved),
  the new track gets a new stream. Both talking at once: two streams, so
  two overlapping turns.
- The interview ends (room closed), nobody is left in the call for
  EMPTY_LEAVE_SECONDS, or the transcriber itself is stopped: the audio heard
  until then is sent, and CloseStream makes Deepgram return the last words
  and close; they are saved first. If Deepgram does not answer within
  FINAL_WAIT_SECONDS, the last live (interim) words are saved instead.
- While listening it writes a heartbeat (transcriber_seen_at), so the room
  shows "Listening"; any problem goes to transcript_problem.
"""

import asyncio
import bisect
import contextlib
import json
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta

import websockets
from livekit import api, rtc
from websockets.exceptions import InvalidStatus

from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import InterviewSession, Job
from app.db.models.interview import SessionStatus, Speaker
from app.interviews.room import room_name
from app.transcriber import deepgram
from app.transcriber.turns import TurnBuilder, TurnState, save_turn

logger = logging.getLogger(__name__)

IDENTITY = "transcriber"
TOPIC = "transcript"  # data-channel topic the interviewer's page listens to
HEARTBEAT_SECONDS = 5
EMPTY_LEAVE_SECONDS = 120  # leave a room nobody has been in for 2 minutes
KEEP_ALIVE_SECONDS = 4  # Deepgram closes after ~10 s without data
PING_SECONDS = 5  # check the Deepgram connection this often ...
PING_TIMEOUT_SECONDS = 10  # ... and give it up after this long without answer
FINAL_WAIT_SECONDS = 6  # how long to wait for the last words at the end
RETRY_WAIT = (1, 2, 4, 8, 15)  # seconds between reconnects (then 15 s)
FRAME_MS = 50  # audio sent to Deepgram in 50 ms pieces (20 messages a second)
BYTES_PER_MS = deepgram.SAMPLE_RATE * 2 // 1000  # 16-bit mono: 32 bytes per ms
MAX_WAITING_SECONDS = 120  # audio kept while Deepgram is slow or out of reach
MAX_WAITING_PIECES = MAX_WAITING_SECONDS * 1000 // FRAME_MS
INTERIM_EVERY_SECONDS = 0.15  # at most ~7 live updates a second per speaker
SPEAKERS = {"interviewer": Speaker.INTERVIEWER, "candidate": Speaker.CANDIDATE}

Push = Callable[[dict, bool], Awaitable[None]]  # (message, reliable)


def speaker_of(identity: str) -> Speaker | None:
    """interviewer-3 → interviewer, candidate-12 → candidate; others None."""
    return SPEAKERS.get(identity.partition("-")[0])


def ticket(session_id: int) -> str:
    """The transcriber's own ticket: this room only, hidden, no audio or
    video. It may send data, which it addresses to the interviewer only."""
    settings = get_settings()
    grants = api.VideoGrants(
        room_join=True,
        room=room_name(session_id),
        hidden=True,
        can_subscribe=True,
        can_publish=False,
        can_publish_data=True,
    )
    return (
        api.AccessToken(
            settings.livekit_api_key, settings.livekit_api_secret.get_secret_value()
        )
        .with_identity(IDENTITY)
        .with_name("Transcriber")
        .with_grants(grants)
        .with_ttl(timedelta(hours=6))
        .to_jwt()
    )


def livekit_ws_url() -> str:
    """LiveKit's address for the real-time connection (ws:// instead of http://)."""
    return get_settings().livekit_url.replace("http", "ws", 1)


def set_problem(session_id: int, problem: str | None) -> None:
    """Show (or clear) why the transcript cannot be written."""
    with SessionLocal() as db:
        session = db.get(InterviewSession, session_id)
        if session is not None and session.transcript_problem != problem:
            session.transcript_problem = problem
            db.commit()


def heartbeat(session_id: int) -> bool:
    """Record that the transcriber listens; False once the interview is over."""
    with SessionLocal() as db:
        session = db.get(InterviewSession, session_id)
        if session is None or session.status != SessionStatus.LIVE:
            return False
        session.transcriber_seen_at = clock.now()
        db.commit()
        return True


def keyterms_for(session_id: int) -> list[str]:
    """The job's requirement names, to help Deepgram with technical words."""
    with SessionLocal() as db:
        session = db.get(InterviewSession, session_id)
        job = db.get(Job, session.job_id) if session else None
        return deepgram.job_keyterms(job.profile if job else None)


def turn_message(row_id: int, speaker: Speaker, turn: TurnState) -> dict:
    """A saved turn as the interviewer's page reads it (same as the API)."""
    return {
        "kind": "turn",
        "turn": {
            "id": row_id,
            "speaker": speaker.value,
            "text": turn.text,
            "start_ms": turn.start_ms,
            "end_ms": turn.end_ms,
        },
    }


@dataclass
class Piece:
    """One piece of a person's audio (usually 50 ms).
    number: counts up from 1, so a piece can be found after older ones are
    forgotten. heard_ms: when it was heard (ms from the interview start).
    stream_end: where it ends in Deepgram's time on the connection that
    last sent it."""

    number: int
    data: bytes
    heard_ms: int
    stream_end: int = 0


class Timeline:
    """Deepgram's times on one connection → interview times.

    Deepgram counts from the first audio byte of a connection. That is not a
    fixed offset from the interview start: a muted microphone sends nothing
    for a while, and after a reconnect older audio is sent first. So each
    piece sent records where it starts in Deepgram's time and when it was
    heard."""

    def __init__(self):
        self.starts: list[int] = []  # ms in Deepgram's time
        self.heard: list[int] = []  # ms from the interview start
        self.end = 0

    def add(self, piece: Piece) -> None:
        """A piece goes out on this connection."""
        self.starts.append(self.end)
        self.heard.append(piece.heard_ms)
        self.end += len(piece.data) // BYTES_PER_MS
        piece.stream_end = self.end

    def to_ms(self, seconds: float) -> int:
        """Deepgram seconds → ms from the interview start."""
        if not self.starts:
            return 0
        stream_ms = round(seconds * 1000)
        i = max(bisect.bisect_right(self.starts, stream_ms) - 1, 0)
        return self.heard[i] + stream_ms - self.starts[i]


class SpeakerStream:
    """One person's microphone → Deepgram → saved turns (and live pushes).

    A reader takes every audio piece from LiveKit at once and keeps it in
    `waiting` until Deepgram has finished it; each connection sends from
    there. last_sent: number of the last piece the current connection
    sent."""

    def __init__(
        self,
        session_id: int,
        started_at,
        speaker: Speaker,
        track,
        keyterms=(),
        push: Push | None = None,
    ):
        self.session_id = session_id
        self.started_at = started_at
        self.speaker = speaker
        self.keyterms = list(keyterms)
        self.push = push
        self.audio = rtc.AudioStream(
            track,
            sample_rate=deepgram.SAMPLE_RATE,
            num_channels=1,
            frame_size_ms=FRAME_MS,
        )
        self.waiting: deque[Piece] = deque()
        self.count = 0  # pieces read so far
        self.last_sent = 0
        self.new_audio = asyncio.Event()  # audio arrived, the track ended or stop
        self.track_ended = False
        self.stopping = asyncio.Event()
        self.stopped_ms: int | None = None  # audio heard after this is not sent
        self.unsaved: deepgram.Interim | None = None  # live words, not final yet
        self.failures = 0
        self._last_interim = 0.0
        self._warned = False

    async def run(self) -> None:
        """Stream until the person leaves or we stop; reconnect to Deepgram
        when it drops (the next connection sends the waiting audio first)."""
        reader = asyncio.create_task(self._read_audio())
        try:
            while True:
                try:
                    await self._stream_once()
                    break  # all audio sent and the last words saved
                except deepgram.DeepgramError as error:
                    self.failures += 1
                    await asyncio.to_thread(set_problem, self.session_id, str(error))
                    logger.warning(
                        "Deepgram problem: session %d, %s", self.session_id, error
                    )
                    if not error.retry:
                        break  # e.g. a refused key: retrying cannot help
                except Exception as error:  # noqa: BLE001 - network drop: try again
                    self.failures += 1
                    logger.warning(
                        "Transcript stream dropped (%s): session %d",
                        type(error).__name__,
                        self.session_id,
                    )
                    if self.failures >= 3:
                        await asyncio.to_thread(
                            set_problem,
                            self.session_id,
                            "Deepgram can't be reached right now: retrying.",
                        )
                if self.stopping.is_set():
                    break  # shutting down: no time for another connection
                wait = RETRY_WAIT[min(self.failures, len(RETRY_WAIT)) - 1]
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.stopping.wait(), timeout=wait)
        finally:
            reader.cancel()
            await self._send_live(
                {"kind": "interim", "speaker": self.speaker.value, "text": ""}
            )
            await self.audio.aclose()

    async def stop(self) -> None:
        """Finish: send the audio heard until now, then save the last words."""
        if not self.stopping.is_set():
            self.stopped_ms = self._now_ms()
            self.stopping.set()
            self.new_audio.set()

    def _now_ms(self) -> int:
        """Milliseconds since the interview started."""
        return max(round((clock.now() - self.started_at).total_seconds() * 1000), 0)

    async def _read_audio(self) -> None:
        """Take every audio piece as soon as LiveKit has it (so a slow
        connection never makes LiveKit drop audio) and keep it waiting."""
        async for event in self.audio:
            data = bytes(event.frame.data)
            self.count += 1
            heard = max(self._now_ms() - len(data) // BYTES_PER_MS, 0)
            self.waiting.append(Piece(self.count, data, heard))
            if len(self.waiting) > MAX_WAITING_PIECES:
                self._drop_oldest()
            self.new_audio.set()
        self.track_ended = True  # the person left (or reconnected)
        self.new_audio.set()

    def _drop_oldest(self) -> None:
        """Deepgram has been away too long: forget the oldest audio."""
        piece = self.waiting.popleft()
        if piece.number > self.last_sent and not self._warned:
            self._warned = True  # this audio never reached Deepgram
            logger.warning(
                "Deepgram away for over %d s, oldest audio dropped: session %d",
                MAX_WAITING_SECONDS,
                self.session_id,
            )

    def _next_piece(self) -> Piece | None:
        """The first waiting piece this connection has not sent yet (never
        audio heard after a stop)."""
        if not self.waiting:
            return None
        index = max(self.last_sent - self.waiting[0].number + 1, 0)
        if index >= len(self.waiting):
            return None
        piece = self.waiting[index]
        if self.stopped_ms is not None and piece.heard_ms > self.stopped_ms:
            return None
        return piece

    def _finished_up_to(self, stream_ms: int) -> None:
        """Deepgram has finished the audio up to stream_ms: forget it."""
        while (
            self.waiting
            and self.waiting[0].number <= self.last_sent
            and self.waiting[0].stream_end <= stream_ms
        ):
            self.waiting.popleft()

    async def _send_live(self, message: dict, reliable: bool = False) -> None:
        """Push to the interviewer's page; a failed push never stops the
        transcript (the page also asks the backend)."""
        if self.push is None:
            return
        with contextlib.suppress(Exception):
            await self.push(message, reliable)

    async def _on_event(self, event, builder: TurnBuilder) -> None:
        """Handle one Deepgram message: live words, a saved turn, a pause."""
        if isinstance(event, deepgram.Interim):
            self.unsaved = event
            now = time.monotonic()
            if now - self._last_interim >= INTERIM_EVERY_SECONDS:
                self._last_interim = now
                await self._send_live(
                    {
                        "kind": "interim",
                        "speaker": self.speaker.value,
                        "text": event.text,
                    }
                )
            return
        if isinstance(event, deepgram.Segment):
            self.unsaved = None  # Deepgram has decided on these words
        turn = builder.feed(event)
        if turn is not None:
            turn.row_id = await asyncio.to_thread(
                save_turn, self.session_id, self.speaker, turn
            )
            # The page replaces this speaker's live words with the saved turn.
            await self._send_live(turn_message(turn.row_id, self.speaker, turn), True)

    async def _keep_last_words(self, builder: TurnBuilder) -> None:
        """Deepgram did not confirm the last words in time (e.g. a slow
        network at the end): save what it showed live rather than lose them."""
        words, self.unsaved = self.unsaved, None
        if words is not None:
            logger.info(
                "Last words kept from the live text: session %d", self.session_id
            )
            last = deepgram.Segment(words.text, words.start, words.end, True)
            await self._on_event(last, builder)

    async def _stream_once(self) -> None:
        """One Deepgram connection: send the waiting audio and save turns.
        Returns once all audio is sent and the last words are saved; raises
        when the connection fails (run() then connects again)."""
        settings = get_settings()
        url = deepgram.listen_url(
            settings.deepgram_model, settings.deepgram_language, self.keyterms
        )
        headers = {
            "Authorization": f"Token {settings.deepgram_api_key.get_secret_value()}"
        }
        try:
            connection = await websockets.connect(
                url,
                additional_headers=headers,
                open_timeout=10,
                ping_interval=PING_SECONDS,
                ping_timeout=PING_TIMEOUT_SECONDS,
            )
        except InvalidStatus as error:
            raise deepgram.error_for(error.response.status_code) from None
        except OSError:
            raise deepgram.error_for(None) from None
        async with connection as ws:
            self.failures = 0
            await asyncio.to_thread(set_problem, self.session_id, None)
            # Start from the oldest audio Deepgram has not finished yet.
            self.last_sent = self.waiting[0].number - 1 if self.waiting else self.count
            self.unsaved = None
            timeline = Timeline()
            builder = TurnBuilder(timeline.to_ms)
            last_sent_at = time.monotonic()

            async def send_audio() -> None:
                """Send the waiting audio in order; return once all of it is
                out and no more will come (the person left, or stopping)."""
                nonlocal last_sent_at
                while True:
                    piece = self._next_piece()
                    if piece is not None:
                        timeline.add(piece)
                        await ws.send(piece.data)
                        self.last_sent = piece.number
                        last_sent_at = time.monotonic()
                    elif self.track_ended or self.stopping.is_set():
                        return
                    else:
                        self.new_audio.clear()
                        await self.new_audio.wait()

            async def keep_alive() -> None:
                """Keep the stream open while the microphone is muted."""
                while True:
                    await asyncio.sleep(KEEP_ALIVE_SECONDS)
                    if time.monotonic() - last_sent_at >= KEEP_ALIVE_SECONDS:
                        await ws.send(deepgram.KEEP_ALIVE)

            async def receive() -> None:
                """Handle every message from Deepgram as it arrives."""
                async for raw in ws:
                    event = deepgram.parse(raw)
                    if isinstance(event, deepgram.Segment):
                        self._finished_up_to(round(event.done_until * 1000))
                    if event is not None:
                        await self._on_event(event, builder)

            receiver = asyncio.create_task(receive())
            sender = asyncio.create_task(send_audio())
            pinger = asyncio.create_task(keep_alive())
            try:
                done, _ = await asyncio.wait(
                    {receiver, sender}, return_when=asyncio.FIRST_COMPLETED
                )
                if receiver in done:  # broke (or closed) before all audio was sent
                    raise receiver.exception() or ConnectionError("stream closed")
                if sender.exception():
                    raise sender.exception()
                # All audio is out: CloseStream makes Deepgram send the last
                # words and close; wait a moment for them.
                with contextlib.suppress(Exception):
                    await ws.send(deepgram.CLOSE_STREAM)
                    await asyncio.wait_for(receiver, FINAL_WAIT_SECONDS)
                await self._keep_last_words(builder)
            finally:
                for task in (receiver, sender, pinger):
                    task.cancel()
                builder.close()


class RoomListener:
    """Listens to one live interview until it ends, is left empty, or the
    transcriber stops."""

    def __init__(self, session_id: int, started_at):
        self.session_id = session_id
        self.started_at = started_at
        self.room = rtc.Room()
        self.streams: dict[str, tuple[SpeakerStream, asyncio.Task]] = {}
        self.keyterms: list[str] = []
        self.leaving = asyncio.Event()

    async def run(self) -> None:
        """Join, listen, and leave cleanly."""
        self.keyterms = await asyncio.to_thread(keyterms_for, self.session_id)
        self.room.on("track_subscribed", self._on_track)
        self.room.on("track_unsubscribed", self._on_track_gone)
        await self.room.connect(livekit_ws_url(), ticket(self.session_id))
        # An old problem (e.g. "not set up" from before the key was added)
        # no longer holds: clear it now, even before anyone unmutes. A real
        # problem is shown again as soon as a stream fails.
        await asyncio.to_thread(set_problem, self.session_id, None)
        logger.info("Transcriber joined: session %d", self.session_id)
        empty_since = None
        try:
            while self.room.isconnected() and not self.leaving.is_set():
                if not await asyncio.to_thread(heartbeat, self.session_id):
                    break  # ended or cancelled
                if self._people():
                    empty_since = None
                elif empty_since is None:
                    empty_since = time.monotonic()
                elif time.monotonic() - empty_since > EMPTY_LEAVE_SECONDS:
                    logger.info(
                        "Nobody in the call: leaving session %d", self.session_id
                    )
                    break
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self.leaving.wait(), HEARTBEAT_SECONDS)
        finally:
            await self._stop_all()
            await self.room.disconnect()
            logger.info("Transcriber left: session %d", self.session_id)

    async def leave(self) -> None:
        """Stop listening (the transcriber is shutting down): the last words
        of every stream are saved first."""
        self.leaving.set()

    async def push(self, message: dict, reliable: bool) -> None:
        """Send a message to the interviewer(s) in the call only."""
        to = [
            p.identity
            for p in self._people()
            if speaker_of(p.identity) == Speaker.INTERVIEWER
        ]
        if to:
            await self.room.local_participant.publish_data(
                json.dumps(message),
                reliable=reliable,
                destination_identities=to,
                topic=TOPIC,
            )

    def _people(self) -> list:
        """The interviewer and the candidate in the call (not anyone else)."""
        return [
            p for p in self.room.remote_participants.values() if speaker_of(p.identity)
        ]

    def _on_track(self, track, publication, participant) -> None:
        """A person's microphone: start transcribing it."""
        speaker = speaker_of(participant.identity)
        if track.kind != rtc.TrackKind.KIND_AUDIO or speaker is None:
            return  # cameras, shared screens and anyone else are ignored
        stream = SpeakerStream(
            self.session_id, self.started_at, speaker, track, self.keyterms, self.push
        )
        self.streams[track.sid] = (stream, asyncio.ensure_future(stream.run()))
        logger.info("Transcribing %s: session %d", speaker.value, self.session_id)

    def _on_track_gone(self, track, publication, participant) -> None:
        """A microphone left (person left or reconnected): finish its stream."""
        entry = self.streams.pop(track.sid, None)
        if entry:
            asyncio.ensure_future(entry[0].stop())

    async def _stop_all(self) -> None:
        """Finish every stream and wait for the last words to be saved."""
        entries = list(self.streams.values())
        self.streams.clear()
        for stream, _task in entries:
            await stream.stop()
        tasks = [task for _stream, task in entries]
        if tasks:
            await asyncio.wait(tasks, timeout=FINAL_WAIT_SECONDS + 4)


async def humans_in_room(session_id: int) -> bool:
    """True when the interviewer or the candidate is in the call (so the
    transcriber does not sit in a forgotten "live" room)."""
    settings = get_settings()
    try:
        async with api.LiveKitAPI(
            settings.livekit_url,
            settings.livekit_api_key,
            settings.livekit_api_secret.get_secret_value(),
        ) as livekit:
            answer = await livekit.room.list_participants(
                api.ListParticipantsRequest(room=room_name(session_id))
            )
    except Exception:  # noqa: BLE001 - no room yet (nobody joined)
        return False
    return any(speaker_of(p.identity) for p in answer.participants)
