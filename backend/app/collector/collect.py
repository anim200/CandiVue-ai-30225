"""One collection round: new form answers → CV files + candidates.

For every answer (row) in the response Sheet:
1. find the job from "Position applied for" (pre-filled as "JOB-12 · title"),
2. skip it without consent, without a CV, if the CV was collected before, or
   if it was sent after the job's closing date (nothing is stored then),
3. check the CV's size and type, then save it in the intake folder,
4. record the candidate as "received", or "rejected" with the reason.
One bad row never stops the others. Logs never contain names or emails.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from app.collector.intake import CvRejected, check_cv, check_cv_size, remove_cv, save_cv
from app.db.database import SessionLocal
from app.db.models import Candidate, Job
from app.db.models.candidate import CandidateStatus
from app.knowledge.files import clean_filename

logger = logging.getLogger(__name__)

JOB_REFERENCE = re.compile(r"\bJOB-(\d+)\b", re.IGNORECASE)
# Drive links in the Sheet look like https://drive.google.com/open?id=<id>
DRIVE_FILE_ID = re.compile(r"(?:[?&]id=|/d/)([\w-]{10,})")

# Words that identify each question's column in the Sheet (first match wins).
COLUMNS = {
    "submitted": ("timestamp",),  # added by Google Forms
    "name": ("full name", "name"),
    "email": ("email",),
    "position": ("position", "role", "job"),
    "cv": ("cv", "resume", "résumé"),
    "consent": ("consent", "agree"),
}


class CollectorSetupError(Exception):
    """The Sheet does not have the expected questions."""


@dataclass
class RoundResult:
    """What one round did (shown in the log)."""

    collected: int = 0
    rejected: int = 0
    skipped: int = 0  # no job reference, no consent or no CV
    late: int = 0  # sent after the job's closing date: not collected
    failed: int = 0  # will be tried again next round


def job_reference(job_id: int, title: str) -> str:
    """The text pre-filled in "Position applied for", e.g. "JOB-12 · Python Developer"."""
    return f"JOB-{job_id} · {title}"


def find_columns(header: list[str]) -> dict[str, int]:
    """Find which column holds each question; raise if one is missing."""
    lowered = [cell.strip().lower() for cell in header]
    columns = {}
    for key, words in COLUMNS.items():
        for word in words:
            index = next((i for i, cell in enumerate(lowered) if word in cell), None)
            if index is not None and index not in columns.values():
                columns[key] = index
                break
        else:
            raise CollectorSetupError(f"The response Sheet has no '{key}' question.")
    return columns


def collect_round(source) -> RoundResult:
    """Collect every new CV from the response Sheet (source: GoogleSource)."""
    result = RoundResult()
    rows = source.response_rows()
    if len(rows) < 2:
        return result  # no answers yet
    columns = find_columns(rows[0])
    zone = ZoneInfo(source.time_zone())
    for number, row in enumerate(rows[1:], start=2):
        try:
            outcome = _collect_row(source, columns, row, zone)
        except Exception as exc:  # noqa: BLE001 - one bad row must not stop the others
            # Only the row number and error type: no personal data in logs.
            logger.warning("CV row %d failed: %s", number, type(exc).__name__)
            result.failed += 1
            continue
        if outcome != "known":
            setattr(result, outcome, getattr(result, outcome) + 1)
    return result


def sheet_time(serial: str, zone: ZoneInfo) -> datetime:
    """A Sheets date-time number (days since 30 Dec 1899, in the Sheet's time
    zone) as a UTC time."""
    day_zero = datetime(1899, 12, 30, tzinfo=zone)  # Sheets counts days from here
    return (day_zero + timedelta(days=float(serial))).astimezone(UTC)


def _collect_row(source, columns: dict[str, int], row: list, zone: ZoneInfo) -> str:
    """Handle one answer; return "collected", "rejected", "skipped", "late"
    or "known"."""

    def cell(key: str) -> str:
        """The answer to one question ("" when Google left the cell out)."""
        index = columns[key]
        return str(row[index]).strip() if index < len(row) else ""

    reference = JOB_REFERENCE.search(cell("position"))
    file_ids = DRIVE_FILE_ID.findall(cell("cv"))
    if not reference or not file_ids or not cell("consent"):
        return "skipped"
    job_id, file_id = int(reference.group(1)), file_ids[0]

    with SessionLocal() as db:
        job = db.get(Job, job_id)
        if job is None:
            return "skipped"  # the reference was changed by hand
        closes = job.applications_close_at
        if closes and sheet_time(cell("submitted"), zone) > closes:
            return "late"  # the form's own time, not when we collect it
        known = db.scalar(
            select(Candidate.id).where(
                Candidate.job_id == job_id, Candidate.drive_file_id == file_id
            )
        )
        if known:
            return "known"

        info = source.file_info(file_id)
        candidate = Candidate(
            job_id=job_id,
            full_name=cell("name")[:200] or None,
            email=cell("email")[:255] or None,
            cv_filename=clean_filename(info.get("name", "")),
            drive_file_id=file_id,
        )
        try:
            check_cv_size(int(info.get("size") or 0))  # before downloading
            data = source.download(file_id)
            file_type = check_cv(data, candidate.cv_filename)
        except CvRejected as exc:
            candidate.status = CandidateStatus.REJECTED
            candidate.parse_error = str(exc)
            db.add(candidate)
            db.commit()
            logger.info("CV rejected for job %d: %s", job_id, exc)
            return "rejected"

        db.add(candidate)
        db.flush()  # gives the candidate its id, used as the file name
        save_cv(job_id, candidate.id, file_type, data)
        try:
            db.commit()
        except Exception:
            remove_cv(job_id, candidate.id)  # no file without a candidate
            raise
        logger.info("CV collected for job %d (candidate %d)", job_id, candidate.id)
        return "collected"
