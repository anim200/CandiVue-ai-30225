"""Interview invitation emails (§4B-4, §4B-8).

The text comes from the knowledge base's Email templates collection (RAG)
and is filled in for each candidate. A template needs a "Subject:" line;
its text runs until a "---" line or a new "# " heading, and these
placeholders are filled: {candidate_name} {job_title} {date} {time}
{duration} {interview_link}. Without a usable template (or if the search
fails), a short standard text is used, so invitations never get stuck.
Emails are plain text and go out through the email MCP server.
"""

import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.ai.errors import AIServiceError
from app.core import clock
from app.core.config import get_settings
from app.db.models import Candidate, InterviewSession, Job
from app.db.models.interview import InvitationStatus
from app.db.models.knowledge import KnowledgeCollection
from app.integrations.email import EmailError, send_email
from app.knowledge.search import search_knowledge

logger = logging.getLogger(__name__)

STANDARD = """Subject: Interview invitation: {job_title}

Hello {candidate_name},

Thank you for applying for the {job_title} role. We would like to invite you
to a video interview.

Date and time: {date}, {time}
Length: about {duration} minutes
Your personal link: {interview_link}

If this time does not suit you, reply to this email.
"""
STANDARD_NAME = "standard text (no template in the knowledge base)"
PREVIEW_LINK = "[private link, made when you confirm]"


def template(db: Session) -> tuple[str, str]:
    """The invitation template from the knowledge base and its file name,
    or the standard text."""
    try:
        passages = search_knowledge(
            db, "interview invitation email", [KnowledgeCollection.EMAIL_TEMPLATES], 3
        )
    except AIServiceError:  # the search model is down: still invite people
        passages = []
    best = next((p for p in passages if "Subject:" in p.text), None)
    return (best.text, best.filename) if best else (STANDARD, STANDARD_NAME)


def compose(
    text: str,
    candidate: Candidate,
    job: Job,
    starts_at: datetime,
    duration: int,
    link: str,
) -> tuple[str, str]:
    """Fill the template for one candidate: (subject, plain-text body)."""
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("Subject:"))
    body = []
    for line in lines[first + 1 :]:
        if line.startswith(("---", "# ")):
            break
        body.append(line)
    local = starts_at.astimezone(clock.local_zone())
    values = {
        "candidate_name": candidate.full_name or "there",
        "job_title": job.title,
        "date": local.strftime("%A %d %B %Y"),
        "time": f"{local.strftime('%H:%M')} ({clock.local_zone().key})",
        "duration": str(duration),
        "interview_link": link,
    }
    subject = lines[first].split(":", 1)[1].strip()
    message = "\n".join(body).strip().replace("**", "")  # no Markdown in email
    for key, value in values.items():
        subject = subject.replace(f"{{{key}}}", value)
        message = message.replace(f"{{{key}}}", value)
    return subject, message


def deliver(
    db: Session, session: InterviewSession, token: str, text: str
) -> str | None:
    """Email the candidate their invitation with the private link and record
    the result on the session. Returns why it failed, or None if sent."""
    candidate = db.get(Candidate, session.candidate_id)
    job = db.get(Job, session.job_id)
    if not candidate.email:
        session.invitation_status = InvitationStatus.FAILED
        return "No email address."
    link = f"{get_settings().app_public_url.rstrip('/')}/join/{token}"
    subject, message = compose(
        text, candidate, job, session.scheduled_at, session.duration_minutes, link
    )
    try:
        send_email(candidate.email, subject, message)
    except EmailError as exc:
        session.invitation_status = InvitationStatus.FAILED
        logger.warning("Invitation email failed: session %d", session.id)
        return str(exc)
    session.invitation_status = InvitationStatus.SENT
    logger.info("Invitation email sent: session %d", session.id)
    return None
