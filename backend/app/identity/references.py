"""Application photos (F7, §4B-15): the face photo an applicant sent with
the Google Form, as CandiVue keeps it, and its deletion (N17, N19).

- The CV Collector processes a photo only once the applicant is invited
  (photos_to_process, save_photo, photo_download_failed): an encrypted face
  embedding and an encrypted small copy (Fernet, FACE_REFERENCE_KEY); the
  original file stays in the form owner's Google Drive.
- photo_state() says, in one word, where an applicant's photo stands.
- job_photos() gives the check-in what it compares with: the invited
  applicant's photo and those of the job's other invited applicants.
- purge_expired() deletes photos RETENTION days after the applicant's last
  interview, and at once when all their interviews were cancelled (run
  every hour). Deleting the candidate or the job deletes them too.
"""

import logging
from datetime import timedelta

import numpy as np
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import ApplicationPhoto, Candidate, InterviewSession
from app.db.models.interview import InvitationStatus, PhotoStatus, SessionStatus
from app.identity.photos import PhotoError, prepare

logger = logging.getLogger(__name__)

MAX_DOWNLOAD_TRIES = 5  # then the photo is left as "could not be downloaded"
ACTIVE = (SessionStatus.SCHEDULED, SessionStatus.LIVE)


def is_set_up() -> bool:
    """True when face data can be stored (the key is in .env)."""
    return get_settings().face_reference_key is not None


def photos_to_process(db: Session) -> list[Candidate]:
    """Invited applicants (invitation emailed, interview still ahead) whose
    photo, sent with consent, has not been processed yet or whose download
    failed fewer than MAX_DOWNLOAD_TRIES times."""
    invited = select(InterviewSession.candidate_id).where(
        InterviewSession.status.in_(ACTIVE),
        InterviewSession.invitation_status == InvitationStatus.SENT,
    )
    rows = db.execute(
        select(Candidate, ApplicationPhoto)
        .outerjoin(ApplicationPhoto, ApplicationPhoto.candidate_id == Candidate.id)
        .where(
            Candidate.id.in_(invited),
            Candidate.photo_file_id.is_not(None),
            Candidate.photo_consent.is_(True),
        )
    ).all()
    return [
        candidate
        for candidate, photo in rows
        if photo is None
        or (
            photo.status == PhotoStatus.DOWNLOAD_FAILED
            and photo.tries < MAX_DOWNLOAD_TRIES
        )
    ]


def save_photo(db: Session, candidate: Candidate, data: bytes) -> PhotoStatus:
    """Process the downloaded photo and keep the result: the encrypted
    embedding and small copy, or only the reason it cannot be used."""
    photo = _photo_row(db, candidate)
    try:
        embedding, small = prepare(data)
    except PhotoError as exc:
        photo.status, photo.embedding, photo.thumbnail = exc.status, None, None
    else:
        cipher = _cipher()
        photo.status = PhotoStatus.READY
        photo.embedding = cipher.encrypt(embedding.astype(np.float32).tobytes())
        photo.thumbnail = cipher.encrypt(small)
    db.commit()
    logger.info("Application photo %s: candidate %d", photo.status, candidate.id)
    return photo.status


def photo_unusable(db: Session, candidate: Candidate, status: PhotoStatus) -> None:
    """Keep only the reason the photo cannot be used (e.g. too large to
    download)."""
    photo = _photo_row(db, candidate)
    photo.status, photo.embedding, photo.thumbnail = status, None, None
    db.commit()
    logger.info("Application photo %s: candidate %d", status, candidate.id)


def photo_download_failed(db: Session, candidate: Candidate) -> None:
    """Count a failed download; later rounds try again (MAX_DOWNLOAD_TRIES)."""
    photo = _photo_row(db, candidate)
    photo.status = PhotoStatus.DOWNLOAD_FAILED
    photo.tries += 1
    db.commit()


def photo_state(db: Session, candidate: Candidate) -> str:
    """Where the applicant's photo stands: "missing" (none sent),
    "no_consent", "pending" (not processed yet), "ready", or the
    PhotoStatus that makes it unusable."""
    if not candidate.photo_file_id:
        return "missing"
    if not candidate.photo_consent:
        return "no_consent"
    photo = db.scalar(
        select(ApplicationPhoto).where(ApplicationPhoto.candidate_id == candidate.id)
    )
    return "pending" if photo is None else str(photo.status)


def thumbnail(db: Session, candidate_id: int) -> bytes | None:
    """The small copy of the applicant's photo (JPEG), when there is one."""
    if not is_set_up():
        return None
    photo = db.scalar(
        select(ApplicationPhoto).where(
            ApplicationPhoto.candidate_id == candidate_id,
            ApplicationPhoto.status == PhotoStatus.READY,
        )
    )
    return _cipher().decrypt(photo.thumbnail) if photo else None


def job_photos(db: Session, session: InterviewSession) -> dict:
    """The embeddings the check-in compares with: the invited applicant's
    own ("own", or None) and the other invited applicants of the same job
    ("others": [(name, embedding)]), to notice if someone else attends."""
    if not is_set_up():
        return {"own": None, "others": []}
    invited = select(InterviewSession.candidate_id).where(
        InterviewSession.job_id == session.job_id
    )
    rows = db.execute(
        select(ApplicationPhoto, Candidate.full_name)
        .join(Candidate, Candidate.id == ApplicationPhoto.candidate_id)
        .where(
            ApplicationPhoto.candidate_id.in_(invited),
            ApplicationPhoto.status == PhotoStatus.READY,
        )
    ).all()
    cipher = _cipher()
    own, others = None, []
    for photo, name in rows:
        vector = np.frombuffer(cipher.decrypt(photo.embedding), dtype=np.float32)
        if photo.candidate_id == session.candidate_id:
            own = vector
        else:
            others.append((name or "another applicant", vector))
    return {"own": own, "others": others}


def forget_photo(db: Session, candidate: Candidate) -> None:
    """The applicant withdrew their consent: delete the processed photo and
    never process it again."""
    candidate.photo_consent = False
    photo = db.scalar(
        select(ApplicationPhoto).where(ApplicationPhoto.candidate_id == candidate.id)
    )
    if photo is not None:
        db.delete(photo)
    db.commit()
    logger.info("Application photo deleted on request: candidate %d", candidate.id)


def purge_expired(db: Session) -> int:
    """Delete the photos of applicants with no interview ahead whose last
    interview ended (or was due) more than FACE_RETENTION_DAYS ago, or whose
    interviews were all cancelled."""
    cutoff = clock.now() - timedelta(days=get_settings().face_retention_days)
    deleted = 0
    for photo in db.scalars(select(ApplicationPhoto)):
        sessions = db.scalars(
            select(InterviewSession).where(
                InterviewSession.candidate_id == photo.candidate_id
            )
        ).all()
        if any(s.status in ACTIVE for s in sessions):
            continue
        held = [
            s.ended_at or s.scheduled_at
            for s in sessions
            if s.status != SessionStatus.CANCELLED
        ]
        if not held or max(held) < cutoff:
            db.delete(photo)
            deleted += 1
    db.commit()
    if deleted:
        logger.info("Application photos deleted after retention: %d", deleted)
    return deleted


def _photo_row(db: Session, candidate: Candidate) -> ApplicationPhoto:
    """The applicant's photo row, created when missing (not yet saved)."""
    photo = db.scalar(
        select(ApplicationPhoto).where(ApplicationPhoto.candidate_id == candidate.id)
    )
    if photo is None:
        photo = ApplicationPhoto(
            candidate_id=candidate.id, status=PhotoStatus.DOWNLOAD_FAILED, tries=0
        )
        db.add(photo)
    return photo


def _cipher() -> Fernet:
    """The encryption key from .env."""
    return Fernet(get_settings().face_reference_key.get_secret_value().encode())
