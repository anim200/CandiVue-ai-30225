"""The shortlist: candidates the interviewer picks from the latest ranking.

The LLM only turns the interviewer's words ("top 5", "everyone above 75",
"skills at least 80 and meets Docker") into criteria; choose() applies them
here, so the result is exact and the same every time. Only ranked candidates
can be shortlisted: excluded and unreadable CVs never are (F1).
"""

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.db.models import Candidate, Job
from app.interviews.ranking import Row


@dataclass
class Criteria:
    """What to pick. Every field is optional; all given ones must hold."""

    top: int | None = None  # the best N of those that match the rest
    min_overall: float | None = None
    rank_from: int | None = None
    rank_to: int | None = None
    minimums: dict[str, int] = field(default_factory=dict)  # e.g. {"skills": 80}
    must_meet: list[str] = field(default_factory=list)  # requirement names
    names: list[str] = field(default_factory=list)

    def is_empty(self) -> bool:
        """True when nothing was asked for."""
        return not (
            self.top
            or self.min_overall is not None
            or self.rank_from
            or self.rank_to
            or self.minimums
            or self.must_meet
            or self.names
        )


def choose(rows: list[Row], requirements: list[str], c: Criteria) -> tuple[list, list]:
    """Apply the criteria to the ranking. Returns the chosen rows (best first)
    and notes for the interviewer (ties, names not found, too few ...)."""
    ranked = [row for row in rows if row.ranked]
    picked = ranked
    notes = []
    if c.names:
        named = []
        for name in c.names:
            hits = [row for row in rows if name.lower() in row.name.lower()]
            if not hits:
                notes.append(f"No applicant called “{name}”.")
            elif len(hits) > 1:
                who = ", ".join(row.name for row in hits)
                notes.append(f"“{name}” matches {len(hits)} people ({who}): say which.")
            elif not hits[0].ranked:
                notes.append(f"{hits[0].name} is not ranked: {hits[0].score.summary}")
            else:
                named.append(hits[0])
        picked = [row for row in picked if row in named]
    first, last = c.rank_from or 1, c.rank_to or len(ranked)
    picked = [row for row in picked if first <= row.score.rank <= last]
    if c.min_overall is not None:
        picked = [row for row in picked if row.score.overall_score >= c.min_overall]
    for dimension, minimum in c.minimums.items():
        picked = [
            row
            for row in picked
            if row.score.dimension_scores[dimension]["score"] >= minimum
        ]
    for wanted in c.must_meet:
        if not any(wanted.lower() in text.lower() for text in requirements):
            notes.append(f"The job profile has no requirement called “{wanted}”.")
            continue
        picked = [row for row in picked if _meets(row, wanted)]
    if c.top:
        if len(picked) < c.top:
            notes.append(f"Only {len(picked)} match, fewer than the {c.top} asked for.")
        elif len(picked) > c.top and (
            picked[c.top].score.overall_score == picked[c.top - 1].score.overall_score
        ):
            notes.append(
                f"{picked[c.top - 1].label()} and {picked[c.top].label()} have the "
                "same score: say if you want both."
            )
        picked = picked[: c.top]
    if not picked and ranked:
        closest = "; ".join(row.label() for row in ranked[:3])
        notes.append(f"Nobody matches. The best ranked are: {closest}.")
    return picked, notes


def save(db: Session, job: Job, action: str, picked: list[Row]) -> None:
    """Change the saved shortlist: "replace" it with the picked candidates,
    "add" them to it, or "remove" them from it."""
    ids = {row.candidate.id for row in picked}
    now = clock.now()
    for candidate in db.scalars(select(Candidate).where(Candidate.job_id == job.id)):
        chosen = candidate.id in ids
        if chosen and action != "remove":
            candidate.shortlisted_at = candidate.shortlisted_at or now  # keep the date
        elif (chosen and action == "remove") or (not chosen and action == "replace"):
            candidate.shortlisted_at = None


def _meets(row: Row, wanted: str) -> bool:
    """True when the CV fully meets the requirement named `wanted`."""
    return any(
        match["status"] == "met" and wanted.lower() in match["requirement"].lower()
        for match in row.score.requirement_matches
    )
