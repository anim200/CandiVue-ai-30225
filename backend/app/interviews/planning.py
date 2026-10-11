"""Interview invitations from the shortlist (F3, §4B-7b): free times, the
checks made before anything is saved, and saving after the interviewer
confirms.

make_plan() checks a request (invite, reschedule or cancel) and returns a
Plan: one item per candidate with its problem (blocks it) or warnings (shown
on the confirmation card), and a preview of the invitation email. The same
checks run again when the interviewer confirms, because time has passed
(apply() skips what is no longer allowed). Invited and moved candidates are
then emailed their private link (app/interviews/emails.py).
Times are stored in UTC and read/typed in local time (app/core/clock.py).
"""

import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_link_token
from app.core import clock
from app.db.models import Candidate, InterviewSession, Job
from app.db.models.interview import SessionStatus
from app.interviews import emails, ranking

WORK_START, WORK_END = time(9), time(17)  # outside these hours: a warning only
MIN_NOTICE = timedelta(hours=1)  # an interview starts at least 1 hour from now
MAX_AHEAD = timedelta(days=90)
MAX_PER_CARD = 20  # one confirmation card stays readable
BREAK = timedelta(minutes=15)  # between interviews suggested by free_slots()
ACTIVE = (SessionStatus.SCHEDULED, SessionStatus.LIVE)


@dataclass
class Plan:
    """What will happen on "Confirm", checked. action: invite / reschedule / cancel."""

    action: str
    duration: int  # minutes
    items: list[dict] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)  # block the whole plan
    warnings: list[str] = field(default_factory=list)
    email: dict | None = None  # preview: subject, text and template name

    @property
    def ok(self) -> bool:
        """True when nothing blocks it."""
        return not self.problems and not any(item["problem"] for item in self.items)

    def as_dict(self) -> dict:
        """The plan as plain data (graph state, confirmation card)."""
        return {
            "action": self.action,
            "duration": self.duration,
            "items": self.items,
            "problems": self.problems,
            "warnings": self.warnings,
            "email": self.email,
        }

    def as_text(self) -> str:
        """The plan for the LLM: what is ready and what must be fixed."""
        lines = [f"{self.action} plan ({self.duration} minutes):"]
        for item in self.items:
            when = (
                clock.local_text(_utc(item["starts_at"])) if item["starts_at"] else ""
            )
            state = f"PROBLEM: {item['problem']}" if item["problem"] else "ok"
            lines.append(
                f"- {item['name']} (id {item['candidate_id']}) {when}: {state}"
            )
        lines += [f"PROBLEM: {p}" for p in self.problems]
        lines += [f"Warning: {w}" for w in self.warnings]
        return "\n".join(lines)


def free_slots(
    db: Session,
    interviewer_id: int,
    days: tuple[date, date],
    hours: tuple[time, time] = (WORK_START, WORK_END),
    count: int = 5,
    duration: int = 45,
    weekdays_only: bool = True,
) -> list[datetime]:
    """Up to `count` free start times (UTC) between the two days, within the
    hours, that do not overlap the interviewer's other interviews."""
    busy = _busy(db, interviewer_id)
    length = timedelta(minutes=duration)
    found = []
    day = days[0]
    while day <= days[1] and len(found) < count:
        start = datetime.combine(day, hours[0], clock.local_zone())
        end = datetime.combine(day, hours[1], clock.local_zone())
        day += timedelta(days=1)
        if weekdays_only and start.weekday() >= 5:
            continue
        while start + length <= end and len(found) < count:
            if start >= clock.now() + MIN_NOTICE and not _overlap(start, length, busy):
                found.append(start)
            start += length + BREAK
    return found


def make_plan(
    db: Session,
    job_id: int,
    interviewer_id: int,
    action: str,
    requested: list[dict],
    duration: int = 45,
    invite_again: bool = False,
) -> Plan:
    """Check a request: [{"candidate_id", "starts_at" (local time)}, ...]."""
    plan = Plan(action, duration)
    job = db.get(Job, job_id)
    unique = list({int(r["candidate_id"]): r for r in requested}.values())
    if not unique:
        plan.problems.append("No candidates were given.")
    if len(unique) > MAX_PER_CARD:
        plan.problems.append(f"At most {MAX_PER_CARD} at a time: narrow the list.")
    rows = {}
    if action == "invite":
        try:
            run, all_rows = ranking.latest_rows(db, job)
        except ValueError as exc:  # not screened (any more): nothing can be sent
            plan.problems.append(str(exc))
        else:
            rows = {row.candidate.id: row for row in all_rows}
            plan.problems += ranking.invitation_blockers(db, job, run)
            if ranking.weights_changed(job, run):
                plan.warnings.append("The weights changed after the last screening.")
    moving = [_active_session(db, job_id, int(r["candidate_id"])) for r in unique]
    busy = _busy(db, interviewer_id, skip={s.id for s in moving if s})
    length = timedelta(minutes=duration)
    for request, session in zip(unique, moving, strict=True):
        candidate = db.get(Candidate, int(request["candidate_id"]))
        item = _item(candidate, session, rows)
        if candidate is None or candidate.job_id != job_id:
            item["problem"] = "Not an applicant for this job."
        elif action == "invite":
            item["problem"] = _invite_problem(
                db, candidate, session, rows, invite_again
            )
        elif session is None:
            item["problem"] = "Has no scheduled interview."
        if action != "cancel" and not item["problem"]:
            start, problem = _start(request.get("starts_at"), length, busy, item)
            item["starts_at"] = start.isoformat() if start else None
            item["problem"] = problem
            if start and not problem:
                busy.append((start, start + length, item["name"]))
        plan.items.append(item)
    ready = [i for i in plan.items if not i["problem"] and i["starts_at"]]
    if ready:  # the email the first one gets (the others: own name and time)
        text, name = emails.template(db)
        candidate = db.get(Candidate, ready[0]["candidate_id"])
        subject, body = emails.compose(
            text,
            candidate,
            job,
            _utc(ready[0]["starts_at"]),
            duration,
            emails.PREVIEW_LINK,
        )
        plan.email = {"subject": subject, "text": body, "template": name}
    return plan


def apply(db: Session, plan: Plan, job_id: int, interviewer_id: int) -> list[dict]:
    """Save a confirmed plan: what passed its checks is done, the rest is
    skipped with the reason. Invited and moved candidates are emailed a new
    private link. Returns one result per candidate."""
    results, to_email = [], []
    for item in plan.items:
        reason = item["problem"] or (plan.problems[0] if plan.problems else None)
        result = {
            "name": item["name"],
            "starts_at": item["starts_at"],
            "done": not reason,
        }
        results.append({**result, "reason": reason, "email": None})
        if reason:
            continue
        session = _active_session(db, job_id, item["candidate_id"])
        if plan.action == "cancel":
            session.status = SessionStatus.CANCELLED
            continue
        token, token_hash = new_link_token()
        if plan.action == "invite":
            session = InterviewSession(
                candidate_id=item["candidate_id"],
                job_id=job_id,
                interviewer_id=interviewer_id,
                duration_minutes=plan.duration,
            )
            db.add(session)
        session.scheduled_at = _utc(item["starts_at"])
        session.join_token_hash = token_hash  # a moved interview gets a new link
        to_email.append((results[-1], session, token))
    db.commit()  # saved first: a failed email never loses an interview
    if to_email:
        text, _ = emails.template(db)
        for result, session, token in to_email:
            result["email"] = emails.deliver(db, session, token, text) or "sent"
        db.commit()
    return results


def new_link_token() -> tuple[str, str]:
    """A new private interview link token and its hash (only the hash is
    stored; the token itself is shown once, in the link)."""
    token = secrets.token_urlsafe(32)
    return token, hash_link_token(token)


def _item(candidate: Candidate | None, session, rows: dict) -> dict:
    """One plan item, as the confirmation card shows it."""
    row = rows.get(candidate.id) if candidate else None
    name = (candidate.full_name or candidate.cv_filename) if candidate else "?"
    return {
        "candidate_id": candidate.id if candidate else 0,
        "name": name,
        "rank": row.score.rank if row else None,
        "overall": row.score.overall_score if row else None,
        "starts_at": None,
        "old_starts_at": session.scheduled_at.isoformat() if session else None,
        "problem": None,
        "warnings": [] if not candidate or candidate.email else ["No email address."],
    }


def _invite_problem(
    db: Session, candidate: Candidate, session, rows: dict, invite_again: bool
) -> str | None:
    """Why this candidate cannot be invited, or None."""
    row = rows.get(candidate.id)
    if row is None or not row.ranked:
        reason = row.score.summary if row else "not in the latest screening."
        return f"Not ranked: {reason}"
    if candidate.shortlisted_at is None:
        return "Not on the shortlist: add them to it first."
    if session is not None:
        return f"Already invited for {clock.local_text(session.scheduled_at)}."
    interviewed = db.scalar(
        select(InterviewSession.id).where(
            InterviewSession.candidate_id == candidate.id,
            InterviewSession.status == SessionStatus.ENDED,
        )
    )
    if interviewed and not invite_again:
        return "Already interviewed: ask again with invite_again to invite them again."
    return None


def _start(text, length, busy, item) -> tuple[datetime | None, str | None]:
    """Read and check a start time; returns (UTC time, problem). Warnings
    (weekend, outside working hours) are added to the item."""
    try:
        start = clock.parse_local(text or "")
    except ValueError:
        return None, "Give a start time as YYYY-MM-DDTHH:MM (local time)."
    if start < clock.now() + MIN_NOTICE:
        return start, "The time is in the past or less than 1 hour away."
    if start > clock.now() + MAX_AHEAD:
        return start, "The time is more than 90 days ahead."
    if clash := _overlap(start, length, busy):
        return start, f"Overlaps {clash}: pick another time."
    local = start.astimezone(clock.local_zone())
    end = local + length
    if local.weekday() >= 5:
        item["warnings"].append("On a weekend.")
    if local.time() < WORK_START or end.time() > WORK_END or end.date() != local.date():
        item["warnings"].append("Outside working hours (09:00–17:00).")
    return start, None


def _busy(db: Session, interviewer_id: int, skip: set[int] = frozenset()) -> list:
    """The interviewer's booked interviews (all jobs): [(start, end, label)]."""
    sessions = db.scalars(
        select(InterviewSession).where(
            InterviewSession.interviewer_id == interviewer_id,
            InterviewSession.status.in_(ACTIVE),
        )
    )
    return [
        (
            s.scheduled_at,
            s.scheduled_at + timedelta(minutes=s.duration_minutes),
            f"another interview at {clock.local_text(s.scheduled_at)}",
        )
        for s in sessions
        if s.id not in skip
    ]


def _overlap(start: datetime, length: timedelta, busy: list) -> str | None:
    """The label of the first booking that overlaps [start, start+length).
    Two times overlap when each one starts before the other ends."""
    end = start + length
    clashes = (
        label for b_start, b_end, label in busy if start < b_end and b_start < end
    )
    return next(clashes, None)


def _active_session(db: Session, job_id: int, candidate_id: int):
    """The candidate's scheduled (or live) interview for this job, if any."""
    return db.scalar(
        select(InterviewSession).where(
            InterviewSession.job_id == job_id,
            InterviewSession.candidate_id == candidate_id,
            InterviewSession.status.in_(ACTIVE),
        )
    )


def _utc(text: str) -> datetime:
    """A stored ISO time (with offset) back as a datetime."""
    return datetime.fromisoformat(text)
