"""Deepgram live speech-to-text over a WebSocket (F4).

One stream per speaker: we send raw audio (16 kHz, 16-bit, mono) as it
arrives and Deepgram sends back JSON results. We only use final results
(is_final): each is a piece of speech with the time of its first and last
word (seconds from the start of that stream; Deepgram's word timestamps,
so silence around the words does not count). An UtteranceEnd message (a
longer pause without words) means the speaker finished a turn. Interim
results (words still being recognised) are only shown live to the
interviewer, never saved.

- mip_opt_out=true: Deepgram may not use the audio to improve its models.
- keyterm (Nova-3): the job's requirement names (e.g. Laravel, Docker) are
  sent as key terms, so technical words are recognised more reliably. Only
  job words, never anything about the candidate.
- While nobody speaks into a muted microphone no audio arrives; Deepgram
  closes a stream after about 10 s without data, so a KeepAlive message is
  sent every few seconds instead.
- CloseStream asks Deepgram to return what it still holds (the last
  words when the interview ends) and then close the stream.
Only this module knows Deepgram's address and message format.
"""

import json
from dataclasses import dataclass
from urllib.parse import urlencode

LISTEN_URL = "wss://api.deepgram.com/v1/listen"
SAMPLE_RATE = 16000  # Hz, what LiveKit gives us after resampling
MAX_KEYTERMS = 50
MAX_KEYTERM_WORDS = 3
KEEP_ALIVE = json.dumps({"type": "KeepAlive"})
CLOSE_STREAM = json.dumps({"type": "CloseStream"})


@dataclass
class Segment:
    """A final piece of speech: text and times (seconds from stream start).
    speech_final: Deepgram heard a pause after it (end of a sentence)."""

    text: str
    start: float
    end: float
    speech_final: bool


@dataclass
class Interim:
    """Words still being recognised (may still change): shown live only."""

    text: str


@dataclass
class UtteranceEnd:
    """A longer pause: the speaker finished what they were saying."""


class DeepgramError(Exception):
    """Deepgram cannot transcribe (the message is safe to show).
    retry: whether trying again later can help."""

    def __init__(self, message: str, retry: bool):
        super().__init__(message)
        self.retry = retry


def listen_url(model: str, language: str, keyterms: list[str] | None = None) -> str:
    """The streaming address with our settings (keyterms: Nova-3 only)."""
    params = {
        "model": model,
        "language": language,
        "encoding": "linear16",
        "sample_rate": SAMPLE_RATE,
        "channels": 1,
        "punctuate": "true",
        "smart_format": "true",
        "interim_results": "true",  # needed for UtteranceEnd messages
        "endpointing": 300,  # ms of silence before Deepgram finalises words
        "utterance_end_ms": 1500,  # ms without words that ends a turn
        "mip_opt_out": "true",  # never used to train Deepgram's models
    }
    query = urlencode(params)
    if keyterms and model.startswith("nova-3"):
        query += "&" + urlencode([("keyterm", term) for term in keyterms])
    return f"{LISTEN_URL}?{query}"


def parse(raw: str | bytes) -> Segment | Interim | UtteranceEnd | None:
    """Read one message from Deepgram; None for what we do not use
    (metadata, speech-started events, empty interim results)."""
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    kind = data.get("type")
    if kind == "UtteranceEnd":
        return UtteranceEnd()
    if kind != "Results":
        return None
    best = (data.get("channel", {}).get("alternatives") or [{}])[0]
    if not data.get("is_final"):
        text = (best.get("transcript") or "").strip()
        return Interim(text) if text else None
    words = best.get("words") or []
    if words:  # the first and last word: exact speech times
        start, end = float(words[0]["start"]), float(words[-1]["end"])
    else:
        start = float(data.get("start", 0.0))
        end = start + float(data.get("duration", 0.0))
    return Segment(
        text=(best.get("transcript") or "").strip(),
        start=start,
        end=end,
        speech_final=bool(data.get("speech_final")),
    )


def error_for(status_code: int | None) -> DeepgramError:
    """A refused connection as a plain-language problem."""
    if status_code in (401, 403):
        return DeepgramError(
            "Deepgram refused the API key: check DEEPGRAM_API_KEY in .env.", retry=False
        )
    if status_code == 402:
        return DeepgramError("The Deepgram account has no credit left.", retry=False)
    if status_code == 429:
        return DeepgramError("Deepgram is busy right now: retrying.", retry=True)
    return DeepgramError("Deepgram can't be reached right now: retrying.", retry=True)


def job_keyterms(profile: dict | None) -> list[str]:
    """Short names from the job's requirements (and the names that count
    for them), e.g. ["PHP", "Laravel", "Docker", "Laravel Sail"]."""
    terms = []
    for requirement in (profile or {}).get("requirements", []):
        names = [requirement.get("text", "")]
        names += requirement.get("also_counts", []) + requirement.get("related", [])
        for name in names:
            name = " ".join(name.split())
            if name and len(name.split()) <= MAX_KEYTERM_WORDS and len(name) <= 40:
                terms.append(name)
    return list(dict.fromkeys(terms))[:MAX_KEYTERMS]
