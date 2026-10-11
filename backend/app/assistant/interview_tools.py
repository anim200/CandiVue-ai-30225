"""The Hiring Assistant's tools after screening (Figure 3: get_ranked_candidates,
schedule_interview): the shortlist and interview invitations.

The LLM passes the interviewer's wishes; app/interviews applies the rules.
Nothing is sent or booked here: propose_invitations, reschedule_interview
and cancel_interview only prepare a checked plan, and the graph then pauses
for the interviewer's Confirm (§4B-7b). Job and interviewer ids come from
the graph state (InjectedState), never from the LLM.
"""

import logging
from datetime import date, time
from typing import Annotated, Literal

from langchain_core.tools import tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core import clock
from app.db.database import SessionLocal
from app.db.models import InterviewSession, Job
from app.interviews import planning, ranking, shortlist

logger = logging.getLogger(__name__)

Minutes = Annotated[int, Field(ge=15, le=180)]


class Invitation(BaseModel):
    """One candidate and the interview's start (local time)."""

    candidate_id: int
    starts_at: str = Field(description="Local time, YYYY-MM-DDTHH:MM")


@tool(response_format="content_and_artifact")
def update_shortlist(
    job_id: Annotated[int, InjectedState("job_id")],
    action: Literal["replace", "add", "remove"] = "replace",
    top: Annotated[int, Field(ge=1, le=50)] | None = None,
    min_overall: Annotated[float, Field(ge=0, le=100)] | None = None,
    rank_from: Annotated[int, Field(ge=1)] | None = None,
    rank_to: Annotated[int, Field(ge=1)] | None = None,
    min_skills: Annotated[int, Field(ge=0, le=100)] | None = None,
    min_experience: Annotated[int, Field(ge=0, le=100)] | None = None,
    min_qualifications: Annotated[int, Field(ge=0, le=100)] | None = None,
    min_ats: Annotated[int, Field(ge=0, le=100)] | None = None,
    must_meet: list[str] | None = None,
    names: list[str] | None = None,
) -> tuple[str, dict]:
    """Shortlist candidates from the latest ranking. Pick them with any of
    the criteria (all given ones must hold): top (best N), min_overall,
    rank_from/rank_to, min_skills/min_experience/min_qualifications/min_ats
    (dimension scores), must_meet (requirement names fully met), names.
    action: "replace" the shortlist, "add" to it or "remove" from it.
    Excluded candidates can never be shortlisted. The interviewer sees the
    saved shortlist as a card."""
    minimums = {
        "skills": min_skills,
        "experience": min_experience,
        "qualifications": min_qualifications,
        "ats": min_ats,
    }
    criteria = shortlist.Criteria(
        top=top,
        min_overall=min_overall,
        rank_from=rank_from,
        rank_to=rank_to,
        minimums={k: v for k, v in minimums.items() if v is not None},
        must_meet=must_meet or [],
        names=names or [],
    )
    if criteria.is_empty():
        raise ValueError("Say who to shortlist, e.g. the top 5 or a minimum score.")
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        run, rows = ranking.latest_rows(db, job)  # ValueError if not screened
        requirements = [r["text"] for r in (job.profile or {}).get("requirements", [])]
        picked, notes = shortlist.choose(rows, requirements, criteria)
        shortlist.save(db, job, action, picked)
        db.commit()
        card = {
            "kind": "shortlist",
            "candidates": [
                _card_row(row) for row in rows if row.candidate.shortlisted_at
            ],
            "notes": notes,
            "warnings": ranking.warnings(db, job, run),
        }
    logger.info("Shortlist updated: job %d, %d listed", job_id, len(card["candidates"]))
    listed = "\n".join(
        f"- {c['name']} (id {c['candidate_id']}, rank {c['rank']}, {c['overall']:.0f})"
        for c in card["candidates"]
    )
    content = f"The shortlist now has {len(card['candidates'])}:\n{listed or '(empty)'}"
    for note in notes + card["warnings"]:
        content += f"\nNote: {note}"
    return content, card


@tool(response_format="content_and_artifact")
def find_free_slots(
    interviewer_id: Annotated[int, InjectedState("interviewer_id")],
    first_day: date,
    last_day: date,
    earliest: time = planning.WORK_START,
    latest: time = planning.WORK_END,
    count: Annotated[int, Field(ge=1, le=planning.MAX_PER_CARD)] = 5,
    duration_minutes: Minutes = 45,
    weekdays_only: bool = True,
) -> tuple[str, dict]:
    """Find free interview start times (local time) between two days, e.g.
    "next week, mornings" = Monday to Friday, earliest 09:00, latest 12:00.
    Times that clash with the interviewer's other interviews are left out."""
    if last_day < first_day or (last_day - first_day).days > 90:
        raise ValueError("Give a range of at most 90 days, first_day before last_day.")
    with SessionLocal() as db:
        slots = planning.free_slots(
            db,
            interviewer_id,
            (first_day, last_day),
            (earliest, latest),
            count,
            duration_minutes,
            weekdays_only,
        )
    times = [clock.local_text(slot) for slot in slots]
    local = [
        slot.astimezone(clock.local_zone()).strftime("%Y-%m-%dT%H:%M") for slot in slots
    ]
    content = (
        "Free times: " + ", ".join(local) if slots else "No free times in that range."
    )
    return content, {"kind": "slots", "times": times}


@tool(response_format="content_and_artifact")
def propose_invitations(
    job_id: Annotated[int, InjectedState("job_id")],
    interviewer_id: Annotated[int, InjectedState("interviewer_id")],
    invitations: list[Invitation],
    duration_minutes: Minutes = 45,
    invite_again: bool = False,
) -> tuple[str, dict]:
    """Prepare interview invitations for shortlisted candidates (one start
    time each, local time). Nothing is sent: the interviewer confirms, changes
    or cancels them on a card. invite_again=true only if the interviewer
    asks to invite someone who was already interviewed."""
    requested = [i.model_dump() for i in invitations]
    return _plan(
        job_id, interviewer_id, "invite", requested, duration_minutes, invite_again
    )


@tool(response_format="content_and_artifact")
def reschedule_interview(
    job_id: Annotated[int, InjectedState("job_id")],
    interviewer_id: Annotated[int, InjectedState("interviewer_id")],
    invitations: list[Invitation],
) -> tuple[str, dict]:
    """Move scheduled interviews to new start times (local time). The
    interviewer confirms the change on a card."""
    requested = [i.model_dump() for i in invitations]
    with SessionLocal() as db:
        duration = (
            _duration(db, job_id, requested[0]["candidate_id"]) if requested else 45
        )
    return _plan(job_id, interviewer_id, "reschedule", requested, duration)


@tool(response_format="content_and_artifact")
def cancel_interview(
    job_id: Annotated[int, InjectedState("job_id")],
    interviewer_id: Annotated[int, InjectedState("interviewer_id")],
    candidate_ids: list[int],
) -> tuple[str, dict]:
    """Cancel the scheduled interviews of these candidates. The interviewer
    confirms on a card."""
    requested = [{"candidate_id": cid} for cid in candidate_ids]
    return _plan(job_id, interviewer_id, "cancel", requested)


INTERVIEW_TOOLS = [
    update_shortlist,
    find_free_slots,
    propose_invitations,
    reschedule_interview,
    cancel_interview,
]


def _plan(job_id, interviewer_id, action, requested, duration=45, invite_again=False):
    """Check the request; a plan with problems goes back to the LLM to fix,
    a clean one becomes the confirmation card (the graph pauses for it)."""
    with SessionLocal() as db:
        plan = planning.make_plan(
            db, job_id, interviewer_id, action, requested, duration, invite_again
        )
    if not plan.ok:
        raise ValueError(plan.as_text())
    card = {"kind": "interview_plan", **plan.as_dict(), "invite_again": invite_again}
    return plan.as_text(), card


def _duration(db, job_id: int, candidate_id: int) -> int:
    """The length of the candidate's scheduled interview (kept when moving it)."""
    length = db.scalar(
        select(InterviewSession.duration_minutes).where(
            InterviewSession.job_id == job_id,
            InterviewSession.candidate_id == candidate_id,
            InterviewSession.status.in_(planning.ACTIVE),
        )
    )
    return length or 45


def _card_row(row: ranking.Row) -> dict:
    """One shortlisted candidate on the card, with the latest scores
    (ranked=False: excluded by a later screening, so it cannot be invited)."""
    return {
        "candidate_id": row.candidate.id,
        "name": row.name,
        "rank": row.score.rank,
        "overall": row.score.overall_score or 0,
        "ranked": row.ranked,
        "scores": {
            k: v["score"] for k, v in (row.score.dimension_scores or {}).items()
        },
    }
