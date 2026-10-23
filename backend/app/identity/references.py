"""Face references (F7): the candidate's consent, the reference they give
before the interview, and its deletion (N17, N19).

- Enrolment: three pictures from the candidate's camera, each with exactly
  one clear face, that agree with each other. Their average embedding is
  stored encrypted (Fernet, FACE_REFERENCE_KEY); the pictures are not kept.
- Declining or withdrawing deletes the reference; the interview goes on
  without an identity check (no penalty).
- purge_expired() deletes references of cancelled interviews and those
  older than FACE_RETENTION_DAYS after the interview (run every hour).
"""

import logging
from datetime import timedelta

import numpy as np
from cryptography.fernet import Fernet
from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import Candidate, FaceReference, InterviewSession
from app.db.models.interview import IdentityConsent, SessionStatus
from app.identity.faces import FaceError, decode_image, face_embedding, similarity

logger = logging.getLogger(__name__)

PICTURES = 3
MAX_PICTURE_BYTES = 2 * 1024 * 1024
SAME_PERSON = 0.5  # the three pictures must agree at least this much
NOT_SAME = (
    "The pictures do not look alike: please take them again with only you in view."
)


class EnrolError(Exception):
    """The pictures cannot be used (the message is safe to show)."""


def is_set_up() -> bool:
    """True when face references can be stored (the key is in .env)."""
    return get_settings().face_reference_key is not None


def enrol(db: Session, session: InterviewSession, pictures: list[bytes]) -> None:
    """Store the candidate's face reference from three pictures (consent
    given); replaces an earlier one."""
    if len(pictures) != PICTURES:
        raise EnrolError(f"Please send {PICTURES} pictures.")
    if any(len(p) > MAX_PICTURE_BYTES for p in pictures):
        raise EnrolError("A picture is too large. Please try again.")
    try:
        vectors = [face_embedding(decode_image(p)) for p in pictures]
    except FaceError as exc:
        raise EnrolError(str(exc)) from None
    if (
        min(similarity(a, b) for i, a in enumerate(vectors) for b in vectors[i + 1 :])
        < SAME_PERSON
    ):
        raise EnrolError(NOT_SAME)
    average = np.mean(vectors, axis=0)
    reference = db.scalar(
        select(FaceReference).where(FaceReference.session_id == session.id)
    )
    if reference is None:
        reference = FaceReference(
            session_id=session.id, candidate_id=session.candidate_id
        )
        db.add(reference)
    reference.embedding = _cipher().encrypt(
        (average / np.linalg.norm(average)).tobytes()
    )
    session.identity_consent = IdentityConsent.GIVEN
    session.identity_consent_at = clock.now()
    db.commit()
    logger.info("Face reference saved: session %d", session.id)


def decline(db: Session, session: InterviewSession) -> None:
    """No identity check: the candidate declined or withdrew their consent.
    Any reference is deleted at once."""
    db.execute(delete(FaceReference).where(FaceReference.session_id == session.id))
    session.identity_consent = IdentityConsent.DECLINED
    session.identity_consent_at = clock.now()
    db.commit()
    logger.info("Identity check declined: session %d", session.id)


def job_references(db: Session, session: InterviewSession) -> dict | None:
    """The references the live check compares with: the invited candidate's
    own, and those of the job's other candidates (to notice if someone else
    attends). None when the invited candidate gave none (no consent: their
    face is never checked)."""
    rows = db.execute(
        select(FaceReference, Candidate.full_name)
        .join(InterviewSession, InterviewSession.id == FaceReference.session_id)
        .join(Candidate, Candidate.id == FaceReference.candidate_id)
        .where(InterviewSession.job_id == session.job_id)
    ).all()
    cipher = _cipher()
    own, others = [], []
    for reference, name in rows:
        vector = np.frombuffer(cipher.decrypt(reference.embedding), dtype=np.float32)
        if reference.candidate_id == session.candidate_id:
            own.append(vector)
        else:
            others.append((name or "another applicant", vector))
    return {"own": own, "others": others} if own else None


def purge_expired(db: Session) -> int:
    """Delete the references of cancelled interviews and of interviews that
    ended (or were due) more than FACE_RETENTION_DAYS ago."""
    cutoff = clock.now() - timedelta(days=get_settings().face_retention_days)
    expired = select(InterviewSession.id).where(
        or_(
            InterviewSession.status == SessionStatus.CANCELLED,
            func.coalesce(InterviewSession.ended_at, InterviewSession.scheduled_at)
            < cutoff,
        )
    )
    deleted = db.execute(
        delete(FaceReference).where(FaceReference.session_id.in_(expired))
    ).rowcount
    db.commit()
    if deleted:
        logger.info("Face references deleted after retention: %d", deleted)
    return deleted


def _cipher() -> Fernet:
    """The encryption key from .env."""
    return Fernet(get_settings().face_reference_key.get_secret_value().encode())
