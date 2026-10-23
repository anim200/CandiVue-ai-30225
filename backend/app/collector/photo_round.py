"""Application photos (F7, §4B-15): once an applicant is invited, download
the face photo they sent with the form (read-only Google Drive access) and
keep only what the check-in needs (app/identity/references.py).

Photos are processed only for invited applicants (data minimisation, N16):
most applicants are never interviewed. A failed download is tried again in
later rounds; an unusable photo gets its reason for the interviewer. One
bad photo never stops the others. Logs never contain names or emails.
"""

import logging
from dataclasses import dataclass

from app.collector.google_source import GoogleSourceError
from app.db.database import SessionLocal
from app.db.models.interview import PhotoStatus
from app.identity import references
from app.identity.photos import MAX_PHOTO_BYTES

logger = logging.getLogger(__name__)


@dataclass
class PhotoRoundResult:
    """What one round did with the invited applicants' photos."""

    ready: int = 0
    unusable: int = 0
    failed: int = 0  # will be tried again next round


def process_photos(source) -> PhotoRoundResult:
    """Download and process the photos of newly invited applicants."""
    result = PhotoRoundResult()
    if not references.is_set_up():
        return result  # no key to encrypt with: the identity check is off
    with SessionLocal() as db:
        for candidate in references.photos_to_process(db):
            try:
                size = int(source.file_info(candidate.photo_file_id).get("size") or 0)
                if size > MAX_PHOTO_BYTES:  # checked before downloading
                    references.photo_unusable(db, candidate, PhotoStatus.TOO_LARGE)
                    result.unusable += 1
                    continue
                data = source.download(candidate.photo_file_id)
            except GoogleSourceError as exc:
                references.photo_download_failed(db, candidate)
                logger.info(
                    "Photo not downloaded (candidate %d): %s", candidate.id, exc
                )
                result.failed += 1
                continue
            status = references.save_photo(db, candidate, data)
            if status == PhotoStatus.READY:
                result.ready += 1
            else:
                result.unusable += 1
    return result
