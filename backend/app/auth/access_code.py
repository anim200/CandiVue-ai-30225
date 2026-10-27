"""The one-time email code that opens a candidate's interview link.

A link can be forwarded, but the code goes only to the email address the
candidate applied with, so someone with just the link cannot get in. The
code has 6 digits, works once, for CODE_MINUTES, with at most MAX_TRIES
wrong guesses; a new one can be asked for after RESEND_SECONDS. Only a hash
keyed with JWT_SECRET is stored, so the database alone does not reveal it.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import timedelta
from html import escape

from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.db.models import Candidate, InterviewSession, Job
from app.integrations.email import EmailError, send_email

logger = logging.getLogger(__name__)

CODE_MINUTES = 10
MAX_TRIES = 5
RESEND_SECONDS = 60
NO_EMAIL = (
    "There is no email address for this invitation. Please contact the interviewer."
)
NOT_SENT = "We couldn't send the code. Please try again in a minute."
EXPIRED = "This code has expired. Ask for a new one."
TOO_MANY = "Too many wrong codes. Ask for a new one."


class AccessCodeError(Exception):
    """The code cannot be sent or is not right (the message is safe to show)."""


def send_code(db: Session, session: InterviewSession, again: bool = False) -> dict:
    """Email a new code unless a valid one was sent moments ago (or, with
    again=True, unless RESEND_SECONDS have not passed). Returns where it
    went (hidden) and the seconds until a new one can be asked for."""
    candidate = db.get(Candidate, session.candidate_id)
    if not candidate.email:
        raise AccessCodeError(NO_EMAIL)
    now = clock.now()
    waited = (
        (now - session.access_code_sent_at).total_seconds()
        if session.access_code_sent_at
        else None
    )
    valid = (
        session.access_code_expires_at is not None
        and session.access_code_expires_at > now
    )
    if valid and waited is not None and (not again or waited < RESEND_SECONDS):
        return _sent(candidate.email, waited)
    code = f"{secrets.randbelow(10**6):06d}"
    job = db.get(Job, session.job_id)
    try:
        send_email(candidate.email, *_email(code, job.title))
    except EmailError:
        logger.warning("Access code not sent: session %d", session.id)
        raise AccessCodeError(NOT_SENT) from None
    session.access_code_hash = _hash(session.id, code)
    session.access_code_sent_at = now
    session.access_code_expires_at = now + timedelta(minutes=CODE_MINUTES)
    session.access_code_tries = 0
    db.commit()
    logger.info("Access code sent: session %d", session.id)
    return _sent(candidate.email, 0)


def check_code(db: Session, session: InterviewSession, code: str) -> None:
    """Accept the right code once; count a wrong one (AccessCodeError)."""
    if (
        session.access_code_hash is None
        or session.access_code_expires_at <= clock.now()
    ):
        raise AccessCodeError(EXPIRED)
    if session.access_code_tries >= MAX_TRIES:
        raise AccessCodeError(TOO_MANY)
    if not hmac.compare_digest(
        session.access_code_hash, _hash(session.id, code.strip())
    ):
        session.access_code_tries += 1
        db.commit()
        left = MAX_TRIES - session.access_code_tries
        raise AccessCodeError(
            f"That code is not right. {left} {'try' if left == 1 else 'tries'} left."
            if left
            else TOO_MANY
        )
    session.access_code_hash = None  # one use only
    db.commit()


def email_hint(email: str) -> str:
    """The address with most of the name hidden, e.g. "m•••@example.com"."""
    name, _, domain = email.partition("@")
    return f"{name[:1]}•••@{domain}"


def _sent(email: str, waited: float | None) -> dict:
    """Where the code went and when a new one may be asked for."""
    return {
        "email_hint": email_hint(email),
        "resend_in": max(0, RESEND_SECONDS - int(waited or 0)),
    }


def _hash(session_id: int, code: str) -> str:
    """The stored form of a code (HMAC-SHA256, keyed with JWT_SECRET)."""
    key = get_settings().jwt_secret.get_secret_value().encode()
    return hmac.new(key, f"{session_id}:{code}".encode(), hashlib.sha256).hexdigest()


def _email(code: str, job_title: str) -> tuple[str, str, str]:
    """(subject, text, html) of the code email."""
    spaced = f"{code[:3]} {code[3:]}"
    subject = "Your interview access code"
    text = (
        f"Your code to open your interview for {job_title}: {spaced}\n\n"
        f"It works once, for {CODE_MINUTES} minutes. If you did not ask for it, "
        "you can ignore this email."
    )
    html = (
        '<div style="font-family:Arial,sans-serif;color:#1A2227;max-width:480px">'
        f"<p>Your code to open your interview for <b>{escape(job_title)}</b>:</p>"
        '<p style="font-size:28px;font-weight:700;letter-spacing:4px;color:#23717A">'
        f"{spaced}</p>"
        f"<p>It works once, for {CODE_MINUTES} minutes. If you did not ask for it, "
        "you can ignore this email.</p></div>"
    )
    return subject, text, html
