"""Does the person at check-in match the application photo? (F7, §4B-15)
The decision rules, the match score, and what the interviewer sees.

At check-in the candidate's three camera pictures are compared with the
photo sent with the application (checkin.py). decide() turns the face
similarities into a state:

- matched: the pictures clearly match the photo (MATCH_FROM on average and
  none clearly below);
- not_confirmed: in between: the interviewer compares the photo with the
  video;
- no_match: clearly a different person;
- other_applicant: clearly closer to another invited applicant of the job.
Before that: waiting (not checked in), declined, failed (no usable
pictures after several tries), no_photo (nothing to compare with) or off.

The match score (0-100 %) is a fixed scale on the face similarity, so the
interviewer can read it at a glance: the "unsure" line is 40 %, SFace's
same-person line 60 %, and FULL_MATCH and above 100 %. It is not a
probability. The candidate never sees the result (N9) and is never
blocked by it: the interviewer decides.
"""

from itertools import pairwise
from statistics import mean

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Candidate, InterviewSession
from app.db.models.interview import IdentityConsent, PhotoStatus
from app.identity import references
from app.identity.photos import TEXTS as PHOTO_TEXTS
from app.interviews import cv_view

FULL_MATCH = 0.70  # similarities from here on show as 100 %
OTHER_MARGIN = 0.10  # another applicant must be clearly closer
MAX_SKILLS = 8
TEXTS = {
    "matched": "Matches the application photo",
    "not_confirmed": "Not confirmed: compare the application photo with the video",
    "no_match": "Different person: does not match the application photo",
    "other_applicant": "Different person: looks like {other}, another applicant for this job",
    "failed": "The check-in did not work (the pictures could not be used): compare the application photo with the video",
    "waiting": "The candidate has not checked in yet",
    "declined": "The candidate chose to continue without the face check",
    "no_photo": "No comparison: {reason}",
    "off": "The identity check is not set up",
}
PHOTO_REASONS = {
    "missing": "no photo was sent with the application.",
    "no_consent": "the applicant did not agree to the use of their photo.",
    "pending": "the application photo has not been processed yet.",
} | {str(status): text[0].lower() + text[1:] for status, text in PHOTO_TEXTS.items()}


def score(similarity: float) -> int:
    """The match score in % for a face similarity (see the module
    docstring): 0 → 0, unsure line → 40, match line → 60, FULL_MATCH → 100."""
    match, unsure = _thresholds()
    points = ((0.0, 0.0), (unsure, 40.0), (match, 60.0), (FULL_MATCH, 100.0))
    if similarity <= 0:
        return 0
    for (low, low_score), (high, high_score) in pairwise(points):
        if similarity <= high:
            return round(
                low_score + (similarity - low) / (high - low) * (high_score - low_score)
            )
    return 100


def decide(similarities: list[float], others: list[tuple[str, list[float]]]) -> dict:
    """The check-in result from the similarities of the camera pictures to
    the application photo, and to the other applicants' photos
    ([(name, similarities)]): {"state", "score", "similarity", "other"}."""
    match, unsure = _thresholds()
    own = mean(similarities)
    closest = max(
        ((name, mean(s)) for name, s in others), key=lambda o: o[1], default=None
    )
    if closest and closest[1] >= match and closest[1] > own + OTHER_MARGIN:
        state, other = "other_applicant", closest[0]
    elif own >= match and min(similarities) >= unsure:
        state, other = "matched", None
    elif own < unsure:
        state, other = "no_match", None
    else:
        state, other = "not_confirmed", None
    return {
        "state": state,
        "score": score(own),
        "similarity": round(own, 3),
        "other": other,
    }


def identity_view(db: Session, session: InterviewSession) -> dict:
    """What the interviewer sees (room panel, waiting-room banner): the
    state in words, the match score, whether the application photo can be
    shown and, on a match only, the candidate's profile."""
    candidate = db.get(Candidate, session.candidate_id)
    photo = references.photo_state(db, candidate)
    result = session.identity_result or {}
    state = _state(session, photo)
    text = TEXTS[state].format(
        other=result.get("other") or "another applicant",
        reason=PHOTO_REASONS.get(photo, "the application photo cannot be used."),
    )
    checked = state in ("matched", "not_confirmed", "no_match", "other_applicant")
    return {
        "state": state,
        "text": text,
        "score": result.get("score") if checked else None,
        "checked_at": result.get("checked_at") if checked else None,
        "photo": {
            "state": photo,
            "available": photo == PhotoStatus.READY,
            "text": None if photo == PhotoStatus.READY else PHOTO_REASONS.get(photo),
        },
        "profile": profile(db, session) if state == "matched" else None,
    }


def identity_summary(db: Session, session: InterviewSession) -> dict:
    """The identity line of the assessment report (F6)."""
    view = identity_view(db, session)
    state = view["state"]
    if state == "matched":
        return {
            "state": "confirmed",
            "text": f"Matched the application photo at check-in (match score {view['score']}%).",
        }
    if state in ("not_confirmed", "no_match", "other_applicant"):
        return {
            "state": "not_confirmed",
            "text": f"{view['text']} (match score {view['score']}% at check-in).",
        }
    return {
        "state": "not_checked",
        "text": f"Not checked: {view['text'][0].lower()}{view['text'][1:]}.",
    }


def profile(db: Session, session: InterviewSession) -> dict:
    """The compact profile shown on a match: name, headline experience, key
    skills, pre-interview score and areas to probe."""
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


def _state(session: InterviewSession, photo: str) -> str:
    """The identity state before any wording."""
    if not references.is_set_up():
        return "off"
    if session.identity_consent == IdentityConsent.DECLINED:
        return "declined"
    if photo != PhotoStatus.READY:
        return "no_photo"
    result = session.identity_result or {}
    return result.get("state") if result.get("state") in TEXTS else "waiting"


def _thresholds() -> tuple[float, float]:
    """The match line and the (lower) unsure line from the settings."""
    settings = get_settings()
    match = settings.face_match_from
    return match, min(settings.face_unsure_from, match - 0.01)
