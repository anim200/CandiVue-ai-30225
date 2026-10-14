"""Live transcript (F4): Deepgram messages, turns, the transcriber's ticket,
a whole stream with a fake Deepgram and fake audio, and the transcript API.

No Deepgram key, no network and no LiveKit server are needed: the audio and
the Deepgram connection are replaced by fakes.
"""

import asyncio
import json
from datetime import timedelta
from types import SimpleNamespace

import jwt
import pytest
from pydantic import SecretStr
from sqlalchemy import select
from websockets.exceptions import InvalidStatus

from app.auth.security import Role, create_access_token, hash_password
from app.core import clock
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Candidate, InterviewSession, Job, TranscriptTurn, User
from app.db.models.interview import InvitationStatus, SessionStatus, Speaker
from app.interviews import planning
from app.transcriber import deepgram, listener
from app.transcriber.turns import MAX_TURN_SECONDS, TurnBuilder, TurnState, save_turn

SECRET = "test-livekit-secret-that-is-long-enough-123"


def results(text, start, duration=1.0, speech_final=False, is_final=True):
    """A Deepgram "Results" message as JSON text."""
    return json.dumps(
        {
            "type": "Results",
            "is_final": is_final,
            "speech_final": speech_final,
            "start": start,
            "duration": duration,
            "channel": {"alternatives": [{"transcript": text}]},
        }
    )


# ---------- Deepgram messages ----------


def test_the_stream_asks_for_our_settings():
    url = deepgram.listen_url("nova-3", "en")

    for part in (
        "model=nova-3",
        "language=en",
        "encoding=linear16",
        "sample_rate=16000",
        "utterance_end_ms=1500",
        "mip_opt_out=true",  # Deepgram may not train on the interview audio
    ):
        assert part in url


def test_only_final_results_and_pauses_are_used():
    final = deepgram.parse(results(" I built the API. ", 2.0, 1.5, speech_final=True))
    timed = json.loads(results("Hello there.", 2.0, 3.0))
    timed["channel"]["alternatives"][0]["words"] = [
        {"word": "hello", "start": 2.4, "end": 2.8},
        {"word": "there", "start": 2.9, "end": 3.3},
    ]

    assert final == deepgram.Segment("I built the API.", 2.0, 3.5, True)
    # With word times, a piece's times are its words', not the audio window's.
    assert deepgram.parse(json.dumps(timed)) == deepgram.Segment(
        "Hello there.", 2.4, 3.3, False
    )
    # Words still being recognised: shown live, never saved; empty ones skipped.
    assert deepgram.parse(results("I bui", 2.0, is_final=False)) == deepgram.Interim(
        "I bui"
    )
    assert deepgram.parse(results("", 2.0, is_final=False)) is None
    # Up to where Deepgram has finished the audio (start + duration), and
    # the times of live words (kept only if Deepgram never confirms them).
    assert final.done_until == 3.5
    live_words = deepgram.parse(json.dumps({**timed, "is_final": False}))
    assert (live_words.start, live_words.end) == (2.4, 3.3)
    assert isinstance(deepgram.parse('{"type": "UtteranceEnd"}'), deepgram.UtteranceEnd)
    assert deepgram.parse('{"type": "Metadata"}') is None
    assert deepgram.parse("not json") is None


def test_refusals_become_plain_problems():
    key = deepgram.error_for(401)
    credit = deepgram.error_for(402)
    busy = deepgram.error_for(429)
    down = deepgram.error_for(None)

    assert "DEEPGRAM_API_KEY" in str(key) and not key.retry
    assert "credit" in str(credit) and not credit.retry
    assert busy.retry and down.retry


# ---------- turns ----------


def test_pieces_grow_one_turn_until_a_real_pause():
    builder = TurnBuilder(lambda seconds: 10_000 + round(seconds * 1000))
    segment = deepgram.Segment

    first = builder.feed(segment("I have five years", 1.0, 2.0, False))
    # Deepgram's sentence end (speech_final) alone does not split the turn:
    # on a choppy line it can come after almost every word.
    grown = builder.feed(segment("of Laravel.", 2.3, 3.0, True))
    still = builder.feed(segment("And Docker.", 3.5, 4.2, True))
    second = builder.feed(segment("Next question.", 6.0, 7.0, False))  # 1.8 s pause
    builder.feed(deepgram.UtteranceEnd())
    third = builder.feed(segment("Okay.", 7.1, 7.5, False))

    assert grown is first and still is first
    assert first.text == "I have five years of Laravel. And Docker."
    assert (first.start_ms, first.end_ms) == (11_000, 14_200)  # from the start
    assert second is not first and third is not second


def test_silence_and_very_long_answers():
    builder = TurnBuilder(lambda seconds: round(seconds * 1000))

    assert builder.feed(deepgram.Segment("", 0.0, 1.0, False)) is None
    long = builder.feed(deepgram.Segment("a", 0.0, 1.0, False))
    builder.feed(deepgram.Segment("b", 1.0, MAX_TURN_SECONDS + 1.0, False))
    after = builder.feed(deepgram.Segment("c", MAX_TURN_SECONDS + 1.0, 50.0, False))

    assert after is not long  # split, so the screen keeps updating


def test_each_track_is_one_speaker():
    assert listener.speaker_of("interviewer-3") == Speaker.INTERVIEWER
    assert listener.speaker_of("candidate-12") == Speaker.CANDIDATE
    assert listener.speaker_of("transcriber") is None


def test_the_transcriber_only_listens(monkeypatch):
    monkeypatch.setattr(get_settings(), "livekit_api_secret", SecretStr(SECRET))

    claims = jwt.decode(listener.ticket(7), SECRET, algorithms=["HS256"])

    video = claims["video"]
    assert claims["sub"] == "transcriber" and video["room"] == "interview-7"
    assert video["hidden"] and video["canSubscribe"]
    # No audio or video; data only, which it addresses to the interviewer.
    assert video["canPublish"] is False and video["canPublishData"] is True


# ---------- with the database ----------


@pytest.fixture
def live(request):
    """A live interview that started 10 s ago, with its interviewer."""
    request.getfixturevalue("database_available")
    with SessionLocal() as db:
        user = User(
            email="stt.tester@example.com",
            full_name="STT Tester",
            password_hash=hash_password("x" * 10),
        )
        job = Job(title="PHP Developer")
        db.add_all([user, job])
        db.flush()
        person = Candidate(job_id=job.id, full_name="Alex Strong", cv_filename="a.pdf")
        db.add(person)
        db.flush()
        session = InterviewSession(
            candidate_id=person.id,
            job_id=job.id,
            interviewer_id=user.id,
            scheduled_at=clock.now(),
            join_token_hash=planning.new_link_token()[1],
            invitation_status=InvitationStatus.SENT,
            status=SessionStatus.LIVE,
            started_at=clock.now() - timedelta(seconds=10),
        )
        db.add(session)
        db.commit()
        data = {"id": session.id, "job": job.id, "user": user.id}
    yield data
    with SessionLocal() as db:
        db.delete(db.get(Job, data["job"]))
        db.delete(db.get(User, data["user"]))
        db.commit()


def turns_of(session_id):
    """The saved turns, in order."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(TranscriptTurn)
                .where(TranscriptTurn.session_id == session_id)
                .order_by(TranscriptTurn.start_ms)
            )
        )


def test_a_growing_turn_is_saved_in_one_row(live):
    turn = TurnState(text="I have", start_ms=1000, end_ms=1500)

    turn.row_id = save_turn(live["id"], Speaker.CANDIDATE, turn)
    turn.text, turn.end_ms = "I have five years.", 3000
    again = save_turn(live["id"], Speaker.CANDIDATE, turn)

    rows = turns_of(live["id"])
    assert again == turn.row_id and len(rows) == 1
    assert rows[0].text == "I have five years." and rows[0].end_ms == 3000


class FakeDeepgram:
    """Stands in for Deepgram's WebSocket: sends `during` while audio flows,
    then `at_close` (the last words) after CloseStream, then closes."""

    def __init__(self, during, at_close):
        self.during, self.at_close = during, at_close
        self.sent = []
        self.closed = asyncio.Event()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def send(self, data):
        """Record what the transcriber sends."""
        self.sent.append(data)
        if data == deepgram.CLOSE_STREAM:
            self.closed.set()

    def __aiter__(self):
        return self._messages()

    async def _messages(self):
        """Results while audio flows, the last words after CloseStream."""
        for message in self.during:
            await asyncio.sleep(0.005)
            yield message
        await self.closed.wait()
        for message in self.at_close:
            yield message


class FakeAudio:
    """A microphone track that sends `frames` audio frames, then ends (the
    person left)."""

    def __init__(self, frames):
        self.frames = frames

    def __aiter__(self):
        return self._frames()

    async def _frames(self):
        """10 ms frames of silence."""
        for _ in range(self.frames):
            await asyncio.sleep(0.005)
            yield SimpleNamespace(frame=SimpleNamespace(data=b"\0\0" * 160))

    async def aclose(self):
        """Nothing to free."""


def fake_stream(monkeypatch, connect, frames=20):
    """Fake audio and Deepgram for a SpeakerStream; returns the options the
    audio stream was opened with."""
    opened = {}

    def audio(*args, **kwargs):
        """Record the options and hand out fake audio."""
        opened.update(kwargs)
        return FakeAudio(frames)

    monkeypatch.setattr(get_settings(), "deepgram_api_key", SecretStr("test-key"))
    monkeypatch.setattr(listener.rtc, "AudioStream", audio)
    monkeypatch.setattr(listener.websockets, "connect", connect)
    monkeypatch.setattr(listener, "RETRY_WAIT", (0.01,) * 5)
    return opened


def test_a_whole_stream_saves_the_turns_and_the_last_words(live, monkeypatch):
    fake = FakeDeepgram(
        during=[
            results("I bui", 1.0, 0.5, is_final=False),  # still being recognised
            results("I built payment APIs", 1.0, 1.0),
            results("in Laravel.", 2.0, 1.0, speech_final=True),
            results("Mostly with Docker.", 5.0, 1.5),  # after a 2 s pause
        ],
        at_close=[results("Thank you.", 6.6, 0.8, speech_final=True)],
    )

    async def connect(url, **kwargs):
        """Hand out the fake connection (and check the key is sent)."""
        assert kwargs["additional_headers"]["Authorization"] == "Token test-key"
        # A connection that stops answering is given up within seconds.
        assert kwargs["ping_timeout"] == listener.PING_TIMEOUT_SECONDS <= 10
        return fake

    opened = fake_stream(monkeypatch, connect)
    with SessionLocal() as db:
        started_at = db.get(InterviewSession, live["id"]).started_at
    pushed = []

    async def push(message, reliable):
        """What the interviewer's page would get at once."""
        pushed.append((message, reliable))

    stream = listener.SpeakerStream(
        live["id"], started_at, Speaker.CANDIDATE, None, push=push
    )
    asyncio.run(asyncio.wait_for(stream.run(), timeout=10))

    rows = turns_of(live["id"])
    turns = [m["turn"] for m, reliable in pushed if m["kind"] == "turn" and reliable]
    live_words = [m["text"] for m, _ in pushed if m["kind"] == "interim"]
    assert {t["id"] for t in turns} == {r.id for r in rows}  # every save pushed
    assert turns[-1]["text"] == "Mostly with Docker. Thank you."
    assert live_words[0] == "I bui" and live_words[-1] == ""  # cleared at the end
    assert opened["frame_size_ms"] == 50  # 50 ms pieces
    assert [r.text for r in rows] == [
        "I built payment APIs in Laravel.",
        "Mostly with Docker. Thank you.",  # the last words after the end
    ]
    assert all(r.speaker == Speaker.CANDIDATE for r in rows)
    assert 10_000 <= rows[0].start_ms < 13_000  # 10 s after the interview started
    assert any(isinstance(data, bytes) for data in fake.sent)  # audio was sent
    assert fake.sent[-1] == deepgram.CLOSE_STREAM


def test_a_refused_key_is_shown_and_not_retried(live, monkeypatch):
    calls = []

    async def connect(url, **kwargs):
        """Deepgram answers 401 (wrong key)."""
        calls.append(url)
        raise InvalidStatus(SimpleNamespace(status_code=401, headers={}, body=b""))

    fake_stream(monkeypatch, connect)
    stream = listener.SpeakerStream(live["id"], clock.now(), Speaker.INTERVIEWER, None)

    asyncio.run(asyncio.wait_for(stream.run(), timeout=10))

    assert len(calls) == 1  # a wrong key does not get better by retrying
    with SessionLocal() as db:
        problem = db.get(InterviewSession, live["id"]).transcript_problem
    assert "DEEPGRAM_API_KEY" in problem


def test_the_heartbeat_stops_after_the_end(live):
    assert listener.heartbeat(live["id"]) is True
    with SessionLocal() as db:
        db.get(InterviewSession, live["id"]).status = SessionStatus.ENDED
        db.commit()

    assert listener.heartbeat(live["id"]) is False


# ---------- the transcript API ----------


def interviewer(data):
    """The interviewer's Authorization header."""
    token = create_access_token(data["user"], Role.INTERVIEWER)
    return {"Authorization": f"Bearer {token}"}


def test_the_room_reads_the_turns_and_the_status(client, live):
    url = f"/api/interviews/{live['id']}/transcript"
    save_turn(
        live["id"], Speaker.INTERVIEWER, TurnState("Tell me about Docker.", 500, 2000)
    )

    starting = client.get(url, headers=interviewer(live)).json()
    listener.heartbeat(live["id"])
    listening = client.get(url, headers=interviewer(live)).json()
    newer = client.get(
        url, params={"since": listening["server_time"]}, headers=interviewer(live)
    ).json()
    listener.set_problem(live["id"], "The Deepgram account has no credit left.")
    problem = client.get(url, headers=interviewer(live)).json()

    assert starting["status"] == "starting"
    assert [t["text"] for t in starting["turns"]] == ["Tell me about Docker."]
    assert starting["turns"][0]["speaker"] == "interviewer"
    assert listening["status"] == "listening"
    assert len(newer["turns"]) <= 1  # only turns changed lately (plus overlap)
    assert problem["status"] == "problem" and "credit" in problem["problem"]


def test_a_live_interview_without_the_transcriber_says_so(client, live):
    with SessionLocal() as db:
        db.get(InterviewSession, live["id"]).started_at = clock.now() - timedelta(
            minutes=2
        )
        db.commit()

    answer = client.get(
        f"/api/interviews/{live['id']}/transcript", headers=interviewer(live)
    ).json()

    assert answer["status"] == "off"


def test_candidates_never_read_the_transcript(client, live):
    token = create_access_token(live["id"], Role.CANDIDATE)

    answer = client.get(
        f"/api/interviews/{live['id']}/transcript",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert answer.status_code == 403


def test_an_empty_key_in_env_counts_as_not_set():
    from app.core.config import Settings

    settings = Settings(deepgram_api_key="", google_service_account_key="  ")

    assert settings.deepgram_api_key is None
    assert settings.google_service_account_key is None


def test_job_words_help_with_technical_terms():
    profile = {
        "requirements": [
            {"text": "PHP", "also_counts": [], "related": []},
            {"text": "Docker", "also_counts": ["Laravel Sail"], "related": ["Podman"]},
            {"text": "Five years of building large web platforms", "also_counts": []},
        ]
    }

    terms = deepgram.job_keyterms(profile)
    url = deepgram.listen_url("nova-3", "en", terms)

    assert terms == ["PHP", "Docker", "Laravel Sail", "Podman"]  # long phrases left out
    assert "keyterm=Laravel+Sail" in url
    assert "keyterm" not in deepgram.listen_url("nova-2", "en", terms)  # Nova-3 only


def test_the_stream_recovers_when_deepgram_drops(live, monkeypatch):
    attempts = []

    async def connect(url, **kwargs):
        """Fails twice (network), then works."""
        attempts.append(url)
        if len(attempts) <= 2:
            raise OSError("network down")
        return FakeDeepgram(during=[results("Back again.", 0.5, 1.0)], at_close=[])

    fake_stream(monkeypatch, connect, frames=10)
    stream = listener.SpeakerStream(live["id"], clock.now(), Speaker.CANDIDATE, None)

    asyncio.run(asyncio.wait_for(stream.run(), timeout=10))

    assert len(attempts) == 3
    assert [r.text for r in turns_of(live["id"])] == ["Back again."]
    with SessionLocal() as db:  # recovered: no problem left on screen
        assert db.get(InterviewSession, live["id"]).transcript_problem is None


def test_turn_times_follow_when_the_audio_was_heard():
    timeline = listener.Timeline()
    # Two 50 ms pieces, the microphone muted for 30 s, then two more.
    for number, heard in [(1, 1000), (2, 1050), (3, 31_000), (4, 31_050)]:
        timeline.add(listener.Piece(number, b"\0" * 1600, heard))

    assert timeline.to_ms(0.02) == 1020
    # Deepgram's 120 ms is 20 ms into the third piece, heard after the pause.
    assert timeline.to_ms(0.12) == 31_020


class NumberedAudio(FakeAudio):
    """Like FakeAudio, but every 10 ms frame says which one it is."""

    async def _frames(self):
        """Frame n is n repeated (320 bytes)."""
        for number in range(1, self.frames + 1):
            await asyncio.sleep(0.005)
            yield SimpleNamespace(frame=SimpleNamespace(data=bytes([number]) * 320))


class LineToDeepgram(FakeDeepgram):
    """A Deepgram connection over a bad line: every send takes `slow`
    seconds; Deepgram confirms the first `confirm` frames, and the line
    breaks after `breaks_after` frames (None: it stays up)."""

    def __init__(self, confirm, breaks_after=None, slow=0.0, words="Hello there."):
        super().__init__(during=[], at_close=[results("Last words.", 0.5, 0.5)])
        self.confirm, self.breaks_after, self.slow = confirm, breaks_after, slow
        self.words = words
        self.broken = asyncio.Event()

    def frames(self):
        """The numbers of the audio frames this connection received."""
        return [data[0] for data in self.sent if isinstance(data, bytes)]

    async def send(self, data):
        """Slow; refuses audio once the line is broken."""
        await asyncio.sleep(self.slow)
        if self.broken.is_set():
            raise ConnectionError("line broken")
        await super().send(data)
        if self.breaks_after and len(self.frames()) >= self.breaks_after:
            self.broken.set()

    async def _messages(self):
        """Confirm the first frames, then break or answer CloseStream."""
        while len(self.frames()) < self.confirm:
            await asyncio.sleep(0.001)
        yield results(self.words, 0.0, self.confirm * 0.01)  # 10 ms per frame
        if self.breaks_after:
            await self.broken.wait()
            raise ConnectionError("line broken")
        await self.closed.wait()
        for message in self.at_close:
            yield message


def test_a_broken_line_loses_no_audio_and_repeats_none(live, monkeypatch):
    lines = [
        LineToDeepgram(confirm=5, breaks_after=12),  # breaks mid-answer
        LineToDeepgram(confirm=3, slow=0.01, words="Back again."),  # slower than speech
    ]

    waiting_lines = list(lines)

    async def connect(url, **kwargs):
        """The next connection."""
        return waiting_lines.pop(0)

    fake_stream(monkeypatch, connect)
    monkeypatch.setattr(listener.rtc, "AudioStream", lambda *a, **k: NumberedAudio(30))
    stream = listener.SpeakerStream(live["id"], clock.now(), Speaker.CANDIDATE, None)

    asyncio.run(asyncio.wait_for(stream.run(), timeout=10))

    first, second = lines[0].frames(), lines[1].frames()
    # The second connection starts with the first frame Deepgram had not
    # finished (6): frames 6-12 went out on the broken line, so again.
    assert first == list(range(1, 13))
    assert second == list(range(6, 31))  # every later frame, in order, once
    assert [r.text for r in turns_of(live["id"])] == [
        "Hello there.",
        "Back again. Last words.",
    ]


class SilentAtTheEnd(FakeDeepgram):
    """Shows live words, then never answers CloseStream (slow network)."""

    async def _messages(self):
        """Live words only, then nothing."""
        for message in self.during:
            await asyncio.sleep(0.005)
            yield message
        await asyncio.Event().wait()  # never comes


def test_the_last_live_words_are_kept_when_deepgram_is_too_slow(live, monkeypatch):
    fake = SilentAtTheEnd(
        during=[
            results("Teamwork matters.", 0.0, 1.0),
            results("I believe that clear", 1.2, 1.0, is_final=False),
        ],
        at_close=[],
    )

    async def connect(url, **kwargs):
        """The fake connection."""
        return fake

    fake_stream(monkeypatch, connect)
    monkeypatch.setattr(listener, "FINAL_WAIT_SECONDS", 0.2)
    stream = listener.SpeakerStream(live["id"], clock.now(), Speaker.CANDIDATE, None)

    asyncio.run(asyncio.wait_for(stream.run(), timeout=10))

    assert [r.text for r in turns_of(live["id"])] == [
        "Teamwork matters. I believe that clear"
    ]


class FakeRoom:
    """Just enough of a LiveKit room to see where a push goes."""

    def __init__(self, identities):
        self.remote_participants = {
            i: SimpleNamespace(identity=identity)
            for i, identity in enumerate(identities)
        }
        self.sent = []
        self.local_participant = SimpleNamespace(publish_data=self._publish)

    async def _publish(self, payload, **kwargs):
        """Record what would be sent."""
        self.sent.append((json.loads(payload), kwargs))


def test_live_text_goes_to_the_interviewer_only(monkeypatch):
    rooms = [
        FakeRoom(["interviewer-1", "candidate-9", "transcriber"]),
        FakeRoom(["candidate-9"]),  # the interviewer stepped out
    ]
    monkeypatch.setattr(listener.rtc, "Room", lambda: rooms.pop(0))
    with_interviewer = listener.RoomListener(9, clock.now())
    candidate_only = listener.RoomListener(9, clock.now())
    message = {"kind": "interim", "speaker": "candidate", "text": "Hello"}

    asyncio.run(with_interviewer.push(message, False))
    asyncio.run(candidate_only.push(message, False))

    ((sent, options),) = with_interviewer.room.sent
    assert sent == message and options["topic"] == "transcript"
    assert options["destination_identities"] == ["interviewer-1"]  # never the candidate
    assert candidate_only.room.sent == []  # no interviewer: nothing is sent
