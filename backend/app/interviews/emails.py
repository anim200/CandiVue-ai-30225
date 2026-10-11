"""Interview invitation emails (§4B-4, §4B-8).

The text comes from the knowledge base's Email templates collection (RAG):
the search finds the template and the whole document is rebuilt from its
passages. A template needs a "Subject:" line; its text runs until a "---"
line or a new "# " heading, and these placeholders are filled:
{candidate_name} {job_title} {date} {time} {time_zone} {duration}
{interview_link}. Without a usable template (or if the search fails), a
standard text is used, so invitations never get stuck.

Each email has a plain-text part and an HTML part built from a fixed,
simple layout: paragraphs, a details table for "- **Label:** value" lines,
and a "Join your interview" button for the private link. All template text
is HTML-escaped; the private link is the only link.
"""

import html
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.errors import AIServiceError
from app.core import clock
from app.core.config import get_settings
from app.db.models import Candidate, InterviewSession, Job, KnowledgeChunk
from app.db.models.interview import InvitationStatus
from app.db.models.knowledge import KnowledgeCollection
from app.integrations.email import EmailError, send_email
from app.knowledge.chunking import join_chunks
from app.knowledge.search import search_knowledge

logger = logging.getLogger(__name__)

STANDARD = """Subject: Interview invitation: {job_title}

Hello {candidate_name},

Thank you for applying for the {job_title} role. We would like to invite you to a video interview.

- **Date and time:** {date}, {time} ({time_zone})
- **Length:** about {duration} minutes
- **Your personal link:** {interview_link}

If this time does not suit you, reply to this email and we will find another one.

Kind regards,
The hiring team
"""
STANDARD_NAME = "standard text (no template in the knowledge base)"
PREVIEW_LINK = "[private link, made when you confirm]"
# A template line at least this long was wrapped by the editor: the next
# line continues the same sentence. Shorter lines ("Kind regards,") are
# real line breaks.
WRAPPED_AT = 60
BRAND = "#23717a"  # the app's teal (design: harbor.6)


@dataclass
class Invitation:
    """One filled-in email: subject, plain text and HTML."""

    subject: str
    text: str
    html: str


def template(db: Session) -> tuple[str, str]:
    """The invitation template from the knowledge base (the whole document)
    and its file name, or the standard text."""
    try:
        passages = search_knowledge(
            db, "interview invitation email", [KnowledgeCollection.EMAIL_TEMPLATES], 3
        )
    except AIServiceError:  # the search model is down: still invite people
        passages = []
    best = next((p for p in passages if "Subject:" in p.text), None)
    if best is None:
        return STANDARD, STANDARD_NAME
    return _whole_document(db, best.document_id), best.filename


def compose(
    text: str,
    candidate: Candidate,
    job: Job,
    starts_at: datetime,
    duration: int,
    link: str,
) -> Invitation:
    """Fill the template for one candidate."""
    local = starts_at.astimezone(clock.local_zone())
    values = {
        "candidate_name": candidate.full_name or "there",
        "job_title": job.title,
        "date": local.strftime("%A %d %B %Y"),
        "time": local.strftime("%H:%M"),
        "time_zone": clock.local_zone().key,
        "duration": str(duration),
        "interview_link": link,
    }
    lines = text.splitlines()
    first = next(i for i, line in enumerate(lines) if line.startswith("Subject:"))
    section = []
    for line in lines[first + 1 :]:
        if line.startswith(("---", "# ")):
            break
        section.append(line)
    filled = "\n".join(section)
    subject = lines[first].split(":", 1)[1].strip()
    for key, value in values.items():
        filled = filled.replace(f"{{{key}}}", value)
        subject = subject.replace(f"{{{key}}}", value)
    blocks = _blocks(filled)
    if link not in filled:  # the link must always be in the invitation
        blocks.append(("list", [f"**Your personal link:** {link}"]))
    return Invitation(subject, _as_text(blocks), _as_html(subject, blocks, link))


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
    email = compose(
        text, candidate, job, session.scheduled_at, session.duration_minutes, link
    )
    try:
        send_email(candidate.email, email.subject, email.text, email.html)
    except EmailError as exc:
        session.invitation_status = InvitationStatus.FAILED
        logger.warning("Invitation email failed: session %d", session.id)
        return str(exc)
    session.invitation_status = InvitationStatus.SENT
    logger.info("Invitation email sent: session %d", session.id)
    return None


def _whole_document(db: Session, document_id: int) -> str:
    """A knowledge-base document's full text, rebuilt from its passages."""
    chunks = db.scalars(
        select(KnowledgeChunk.text)
        .where(KnowledgeChunk.document_id == document_id)
        .order_by(KnowledgeChunk.position)
    ).all()
    return join_chunks(list(chunks))


def _blocks(text: str) -> list[tuple[str, list[str]]]:
    """Split the email text into ("paragraph", lines) and ("list", items).
    Lines the editor wrapped are joined back into whole sentences."""
    blocks: list[tuple[str, list[str]]] = []
    for raw in text.splitlines():
        line = raw.strip()
        kind, items = blocks[-1] if blocks else (None, [])
        if not line:
            blocks.append(("gap", []))  # an empty line ends the block
        elif line.startswith("- "):
            if kind == "list":
                items.append(line[2:])
            else:
                blocks.append(("list", [line[2:]]))
        elif kind == "list" and raw.startswith(" "):
            items[-1] += " " + line  # an item continued on the next line
        elif kind == "paragraph":
            if len(items[-1]) >= WRAPPED_AT:  # a long line: the sentence goes on
                items[-1] += " " + line
            else:
                items.append(line)
        else:
            blocks.append(("paragraph", [line]))
    return [block for block in blocks if block[0] != "gap"]


def _label(item: str) -> tuple[str | None, str]:
    """ "**Date and time:** Monday ..." -> ("Date and time", "Monday ...")."""
    match = re.match(r"\*\*(.+?)\*\*\s*(.*)", item)
    if not match:
        return None, item.replace("**", "")
    return match[1].rstrip(":").strip(), match[2].replace("**", "")


def _as_text(blocks: list) -> str:
    """The plain-text part: whole sentences, "Label: value" lines."""
    parts = []
    for kind, items in blocks:
        if kind == "paragraph":
            parts.append("\n".join(items).replace("**", ""))
        else:
            rows = [_label(item) for item in items]
            parts.append("\n".join(f"{k}: {v}" if k else f"- {v}" for k, v in rows))
    return "\n\n".join(parts)


def _as_html(subject: str, blocks: list, link: str) -> str:
    """The HTML part: a simple, mobile-friendly card (tables and inline
    styles, which email programs understand). Everything is escaped."""
    safe_link = html.escape(link, quote=True)
    body = []
    for kind, items in blocks:
        if kind == "paragraph":
            lines = "<br>".join(html.escape(line.replace("**", "")) for line in items)
            lines = lines.replace(
                html.escape(link),
                f'<a href="{safe_link}" style="color:{BRAND}">{safe_link}</a>',
            )
            body.append(f'<p style="margin:0 0 16px">{lines}</p>')
            continue
        rows, has_link = [], False
        for item in items:
            label, value = _label(item)
            if link in value:
                has_link = True  # shown as the button below the table
                continue
            label_cell = (
                f'<td style="padding:6px 16px 6px 0;color:#66717a;white-space:nowrap;'
                f'vertical-align:top">{html.escape(label)}</td>'
                if label
                else '<td style="padding:6px 16px 6px 0;color:#66717a">&bull;</td>'
            )
            rows.append(
                f'<tr>{label_cell}<td style="padding:6px 0;font-weight:600">'
                f"{html.escape(value)}</td></tr>"
            )
        if rows:
            body.append(
                '<table role="presentation" style="width:100%;margin:0 0 20px;'
                'border-collapse:collapse;background:#f5f7f8;border-radius:8px">'
                f'<tr><td style="padding:12px 16px"><table role="presentation" '
                f'style="border-collapse:collapse">{"".join(rows)}</table></td></tr></table>'
            )
        if has_link:
            body.append(
                f'<p style="margin:0 0 8px"><a href="{safe_link}" style="display:inline-block;'
                f"background:{BRAND};color:#ffffff;text-decoration:none;font-weight:600;"
                f'padding:12px 24px;border-radius:6px">Join your interview</a></p>'
                '<p style="margin:0 0 20px;font-size:13px;color:#66717a">If the button does '
                f'not work, open this link: <a href="{safe_link}" style="color:{BRAND}">'
                f"{safe_link}</a></p>"
            )
    return (
        '<!doctype html><html><body style="margin:0;padding:24px 12px;background:#eef1f3;'
        "font-family:Segoe UI,Arial,sans-serif;font-size:15px;line-height:1.6;"
        'color:#1a2227"><table role="presentation" style="max-width:600px;margin:0 auto;'
        'width:100%;border-collapse:collapse;background:#ffffff;border:1px solid #dee3e6">'
        f'<tr><td style="background:{BRAND};color:#ffffff;padding:18px 28px;'
        f'font-size:18px;font-weight:600">{html.escape(subject)}</td></tr>'
        f'<tr><td style="padding:28px">{"".join(body)}</td></tr>'
        '<tr><td style="padding:16px 28px;border-top:1px solid #e9ecee;font-size:12px;'
        'color:#66717a">This link is personal: please do not share it.</td></tr>'
        "</table></body></html>"
    )
