"""Check-in (F7, §4B-15): after the emailed code, the candidate takes three
camera pictures, which are compared with the photo sent with the
application. The pictures are only looked at in memory, never saved.

Each picture must show exactly one clear face in enough light; otherwise
the candidate is told what to change and takes them again (at most
MAX_ATTEMPTS times; after that they continue without). The result is saved
for the interviewer (matching.decide); the candidate only learns that they
are checked in (N9). Declining is always possible and has no effect on the
interview.
"""

import logging

from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Candidate, InterviewSession
from app.db.models.interview import IdentityConsent
from app.identity import faces, matching, references

logger = logging.getLogger(__name__)

PICTURES = 3
MAX_PICTURE_BYTES = 2 * 1024 * 1024
MAX_ATTEMPTS = 10
SAME_PERSON = 0.5  # the three pictures must agree at least this much
NOT_SAME = (
    "The pictures do not look alike: please take them again with only you in view."
)
NO_PHOTO = "There is no application photo to compare with: please continue to the waiting room."
TOO_MANY = (
    "The check-in did not work after several tries. Please continue to the "
    "waiting room; the interviewer will confirm it is you."
)


class CheckInError(Exception):
    """The pictures cannot be used (the message is safe to show)."""


def can_check_in(db: Session, session: InterviewSession) -> bool:
    """True when the candidate should be asked to check in: the identity
    check is set up, their application photo is ready, and they have not
    checked in or declined yet."""
    candidate = db.get(Candidate, session.candidate_id)
    return (
        references.is_set_up()
        and session.identity_consent is None
        and references.photo_state(db, candidate) == "ready"
    )


def check_in(db: Session, session: InterviewSession, pictures: list[bytes]) -> None:
    """Compare three camera pictures with the application photo and save the
    result. CheckInError (with what to change) when the pictures are
    unusable; on the last allowed try the check-in is recorded as failed,
    so the candidate can continue and the interviewer knows why."""
    result = dict(session.identity_result or {})
    attempts = result.get("attempts", 0) + 1
    if attempts > MAX_ATTEMPTS:
        raise CheckInError(TOO_MANY)
    session.identity_result = result | {"attempts": attempts}
    db.commit()  # every try counts, also the ones refused below
    try:
        _compare(db, session, pictures, attempts)
    except CheckInError:
        if attempts < MAX_ATTEMPTS:
            raise
        session.identity_result = {"state": "failed", "attempts": attempts}
        session.identity_consent = IdentityConsent.GIVEN
        session.identity_consent_at = clock.now()
        db.commit()
        logger.info("Check-in failed after %d tries: session %d", attempts, session.id)
        raise CheckInError(TOO_MANY) from None


def _compare(
    db: Session, session: InterviewSession, pictures: list[bytes], attempts: int
) -> None:
    """One try: check the pictures, compare them with the photos, save."""
    if len(pictures) != PICTURES:
        raise CheckInError(f"Please send {PICTURES} pictures.")
    if any(len(p) > MAX_PICTURE_BYTES for p in pictures):
        raise CheckInError("A picture is too large. Please try again.")
    photos = references.job_photos(db, session)
    if photos["own"] is None:
        raise CheckInError(NO_PHOTO)
    try:
        vectors = [_live_face(p) for p in pictures]
    except faces.FaceError as exc:
        raise CheckInError(str(exc)) from None
    if (
        min(
            faces.similarity(a, b)
            for i, a in enumerate(vectors)
            for b in vectors[i + 1 :]
        )
        < SAME_PERSON
    ):
        raise CheckInError(NOT_SAME)

    decision = matching.decide(
        [faces.similarity(v, photos["own"]) for v in vectors],
        [
            (name, [faces.similarity(v, other) for v in vectors])
            for name, other in photos["others"]
        ],
    )
    session.identity_result = decision | {
        "checked_at": clock.now().isoformat(),
        "attempts": attempts,
    }
    session.identity_consent = IdentityConsent.GIVEN
    session.identity_consent_at = clock.now()
    db.commit()
    logger.info("Check-in done: session %d, %s", session.id, decision["state"])


def decline(db: Session, session: InterviewSession) -> None:
    """No face check: the candidate declined, or withdrew their consent
    later. Their result and processed application photo are deleted at
    once; the interview goes ahead as normal."""
    session.identity_consent = IdentityConsent.DECLINED
    session.identity_consent_at = clock.now()
    session.identity_result = None
    db.commit()
    references.forget_photo(db, db.get(Candidate, session.candidate_id))
    logger.info("Face check declined: session %d", session.id)


def _live_face(data: bytes):
    """The face embedding of one camera picture: exactly one face, large
    and light enough (FaceError otherwise)."""
    image = faces.decode_image(data)
    face = faces.find_face(image)
    faces.check_light(image, face)
    return faces.face_embedding(image, face)
