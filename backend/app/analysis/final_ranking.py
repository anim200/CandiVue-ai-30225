"""The final ranking of a job's interviewed candidates (§4B-15 f): only
candidates whose assessment report the interviewer approved, by the overall
score of the report (the average of the CV and interview scores, F6).

- Higher overall score first; on the same overall score the higher
  interview score first; candidates equal on both share a rank (1, 2, 2, 4).
- A candidate interviewed more than once is ranked on their latest
  interview only.
- Everyone else is listed with the reason they are not ranked yet.
The ranking only orders; the interviewer decides whom to select.
"""

from dataclasses import dataclass
from datetime import datetime

NOT_RANKED = {
    "no_report": "The report is being prepared.",
    "failed": "The report could not be prepared.",
    "pending_review": "The report is waiting for your review.",
    "changes_requested": "You asked for changes to the report.",
    "no_score": "Not enough evidence for an overall score.",
    "earlier": "An earlier interview of this candidate; the latest one counts.",
}


@dataclass(frozen=True)
class Entry:
    """One ended interview of the job, as the ranking needs it."""

    interview_id: int
    candidate_id: int
    held_at: datetime
    # "approved", "pending_review", "changes_requested", "failed" or "no_report"
    report: str
    overall: int | None = None
    interview: int | None = None


def rank(entries: list[Entry]) -> dict[int, tuple[int | None, str | None]]:
    """Per interview id: (rank, None) when ranked, or (None, reason)."""
    latest: dict[int, Entry] = {}
    for entry in entries:
        kept = latest.get(entry.candidate_id)
        if kept is None or (entry.held_at, entry.interview_id) > (
            kept.held_at,
            kept.interview_id,
        ):
            latest[entry.candidate_id] = entry
    result: dict[int, tuple[int | None, str | None]] = {}
    ranked = []
    for entry in entries:
        if latest[entry.candidate_id] is not entry:
            result[entry.interview_id] = (None, NOT_RANKED["earlier"])
        elif entry.report != "approved":
            result[entry.interview_id] = (None, NOT_RANKED[entry.report])
        elif entry.overall is None:
            result[entry.interview_id] = (None, NOT_RANKED["no_score"])
        else:
            ranked.append(entry)

    def key(entry: Entry) -> tuple[int, int]:
        """What decides the order: overall score, then interview score."""
        return (entry.overall, entry.interview if entry.interview is not None else -1)

    ranked.sort(key=key, reverse=True)
    for position, entry in enumerate(ranked, start=1):
        tied_with_previous = position > 1 and key(ranked[position - 2]) == key(entry)
        previous_rank = (
            result[ranked[position - 2].interview_id][0] if tied_with_previous else None
        )
        result[entry.interview_id] = (previous_rank or position, None)
    return result
