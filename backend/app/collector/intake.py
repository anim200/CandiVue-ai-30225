"""The CV intake folder: a Docker named volume, never in the repository (N14, D5).

Each job has its own folder, and each CV is saved under its candidate's id
with the type found from the file's content, e.g. job-12/34.pdf. The
original file name is kept only in the database. Files are checked before
they are saved (N8): PDF or Word (DOCX) only, and not too large.
"""

from pathlib import Path

from app.core.config import get_settings
from app.knowledge.files import DocumentError, detect_file_type

CV_TYPES = {"pdf", "docx"}
WRONG_TYPE = "Only PDF or Word (DOCX) CVs are accepted."
TOO_BIG = "The CV is larger than {mb} MB."


class CvRejected(Exception):
    """The CV cannot be used; the message is safe to show to the interviewer."""


def check_cv_size(size: int) -> None:
    """Refuse a CV larger than MAX_CV_MB (checked before downloading it)."""
    max_mb = get_settings().max_cv_mb
    if size > max_mb * 1024 * 1024:
        raise CvRejected(TOO_BIG.format(mb=max_mb))


def check_cv(data: bytes, filename: str) -> str:
    """Return "pdf" or "docx" from the file's content, or raise CvRejected."""
    check_cv_size(len(data))
    try:
        file_type = detect_file_type(data, filename)
    except DocumentError:
        raise CvRejected(WRONG_TYPE) from None
    if file_type not in CV_TYPES:  # e.g. a .txt file
        raise CvRejected(WRONG_TYPE)
    return file_type


def cv_folder(job_id: int) -> Path:
    """The folder that holds one job's CVs."""
    return Path(get_settings().cv_intake_dir) / f"job-{job_id}"


def save_cv(job_id: int, candidate_id: int, file_type: str, data: bytes) -> Path:
    """Save a checked CV. Written to a temporary name first, so a half-written
    file is never mistaken for a CV."""
    folder = cv_folder(job_id)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{candidate_id}.{file_type}"
    temporary = path.with_suffix(".part")
    temporary.write_bytes(data)
    temporary.replace(path)
    return path


def find_cv(job_id: int, candidate_id: int) -> Path | None:
    """The saved CV file of a candidate, or None if there is none."""
    for file_type in CV_TYPES:
        path = cv_folder(job_id) / f"{candidate_id}.{file_type}"
        if path.exists():
            return path
    return None


def remove_cv(job_id: int, candidate_id: int) -> None:
    """Delete a candidate's CV file (used when the candidate is deleted, N19)."""
    path = find_cv(job_id, candidate_id)
    if path is not None:
        path.unlink()
