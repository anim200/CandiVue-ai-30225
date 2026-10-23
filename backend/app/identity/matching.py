"""Who is in the call? (F7) The decision rules, and what the interviewer
sees: the identity state and, on a confident match only, a short profile.

The live check (app/identity/watcher.py) compares a camera picture every
few seconds with the face references. decide() looks at the last WINDOW
pictures together, so one bad frame never decides anything, and never
assumes identity:

- matched: at least two pictures clearly show the invited candidate
  (MATCH_FROM) and none clearly does not (LOW_FROM);
- low_confidence: somewhere in between (the profile stays hidden);
- no_match: clearly not them, or clearly another applicant of the job;
- no_face / several_faces / camera_off: nothing usable to compare;
- checking: not enough pictures yet; no_reference: no consent given.

SFace's own same-person threshold is a cosine similarity of 0.363
(OpenCV); MATCH_FROM keeps a margin above it.
"""

from dataclasses import dataclass
from statistics import mean

from sqlalchemy.orm import Session

from app.analysis.transcript import clock_text
from app.db.models import InterviewSession
from app.db.models.interview import IdentityConsent
from app.interviews import cv_view

MATCH_FROM = 0.40
LOW_FROM = 0.28
WINDOW = 3  # pictures looked at together
OTHER_MARGIN = 0.10  # another applicant must be clearly closer
MAX_SKILLS = 8
TEXTS = {
    "matched": "Identity confirmed",
    "low_confidence": "Low confidence: the face is not clear enough to confirm",
    "no_match": "No match with the invited candidate's reference",
    "no_face": "No face in view",
    "several_faces": "More than one face in view",
    "camera_off": "Camera off or no picture",
    "checking": "Checking…",
    "no_reference": "No face reference: the candidate did not consent",
    "off": "Identity check is not set up",
}


@dataclass(frozen=True)
class Sample:
    """One camera picture compared with the references: the similarity to
    the invited candidate, the closest other applicant (name, similarity),
    or the problem that made the picture unusable."""

    own: float | None = None
    other: tuple[str, float] | None = None
    problem: str | None = None  # no_face, several_faces, too_small, camera_off


def decide(samples: list[Sample]) -> dict:
    """The identity state from the last WINDOW pictures (see the module
    docstring): {"state", "similarity", "other"}."""
    recent = samples[-WINDOW:]
    usable = [s for s in recent if s.own is not None]
    if len(usable) < 2:
        if len(recent) == WINDOW:  # most pictures were unusable
            problem = recent[-1].problem or "no_face"
            return _result("no_face" if problem == "too_small" else problem)
        return _result("checking")
    own = mean(s.own for s in usable)
    best_other = max(
        (s.other for s in usable if s.other), key=lambda o: o[1], default=None
    )
    if (
        best_other
        and best_other[1] >= MATCH_FROM
        and best_other[1] > own + OTHER_MARGIN
    ):
        return _result("no_match", own, best_other[0])
    clear = sum(s.own >= MATCH_FROM for s in usable)
    if clear >= 2 and min(s.own for s in usable) >= LOW_FROM:
        return _result("matched", own)
    if own < LOW_FROM:
        return _result("no_match", own)
    return _result("low_confidence", own)


def identity_view(db: Session, session: InterviewSession, set_up: bool) -> dict:
    """What the interviewer's identity panel shows: the state in words, the
    similarity, when it was checked and, only on a confident match, the
    candidate's profile."""
    result = session.identity_result or {}
    if not set_up:
        state = "off"
    elif session.identity_consent != IdentityConsent.GIVEN:
        state = "no_reference"
    else:
        state = result.get("state", "checking")
    text = TEXTS[state]
    if state == "no_match" and result.get("other"):
        text += f": looks like {result['other']}, another applicant for this job"
    return {
        "state": state,
        "text": text,
        "similarity": result.get("similarity"),
        "checked_at": result.get("checked_at"),
        "confirmed_at_ms": result.get("confirmed_at_ms"),
        "consent_at": session.identity_consent_at,
        "profile": profile(db, session) if state == "matched" else None,
    }


def identity_summary(session: InterviewSession) -> dict:
    """The identity line of the assessment report (F6)."""
    result = session.identity_result or {}
    if session.identity_consent != IdentityConsent.GIVEN:
        return {
            "state": "not_checked",
            "text": "Not checked: no face reference was given.",
        }
    confirmed = result.get("confirmed_at_ms")
    if confirmed is not None and result.get("state") == "matched":
        return {
            "state": "confirmed",
            "text": f"Confirmed by face recognition at {clock_text(confirmed)} "
            "against the reference given with consent.",
        }
    state = result.get("state", "checking")
    return {"state": "not_confirmed", "text": f"Not confirmed: {TEXTS[state].lower()}."}


def profile(db: Session, session: InterviewSession) -> dict:
    """The compact profile shown on a confident match: name, headline
    experience, key skills, pre-interview score and areas to probe."""
    cv = cv_view.overview(db, session)
    screening = cv["screening"] or {}
    latest = next((j["title"] for j in cv["jobs"] if j.get("title")), None)
    headline = ", ".join(
        part
        for part in (
            f"About {cv['years']:g} years of experience"
            if cv["years"] is not None
            else None,
            f"latest role: {latest}" if latest else None,
        )
        if part
    )
    probe = [
        f"{m['requirement']}: {'partly met' if m['status'] == 'partial' else 'not shown'} in the CV"
        for m in screening.get("matches", [])
        if m["status"] != "met"
    ]
    if cv["years"] is None:
        probe.append("Years of experience: not readable from the CV")
    return {
        "name": cv["name"],
        "headline": headline or None,
        "skills": [
            s.strip()
            for s in (cv["skills"] or "").replace("\n", ",").split(",")
            if s.strip()
        ][:MAX_SKILLS],
        "score": screening.get("overall"),
        "rank": screening.get("rank"),
        "ranked_count": screening.get("ranked_count"),
        "probe": probe,
    }


def _result(
    state: str, similarity: float | None = None, other: str | None = None
) -> dict:
    """A decision as stored and shown."""
    return {
        "state": state,
        "similarity": None if similarity is None else round(similarity, 2),
        "other": other,
    }
