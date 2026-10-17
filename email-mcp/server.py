"""Email MCP server: sends interview invitations by email (§4B-4, §4B-6).

The Hiring Assistant (LangGraph 1) calls this server's single tool,
send_email, through MCP after the interviewer confirmed the interviews.
Only this container holds the email login, so the backend never sees it
(least privilege). It has no port on the host: only other containers in
Docker's network can reach it. Each email has a plain-text part and,
optionally, an HTML part (built and escaped by the backend from a fixed
layout) and a calendar invite (invite.ics): the candidate's calendar app
adds the interview, moves it (same uid, later sequence) or removes it
(method CANCEL). The invite's organizer is the sending address.

Settings (environment / .env):
  SMTP_HOST, SMTP_PORT (SSL, e.g. smtp.gmail.com and 465), SMTP_USER,
  SMTP_PASSWORD (a Gmail app password), EMAIL_FROM_NAME.
  EMAIL_TEST_RECIPIENT: when set, EVERY email goes to this address instead
  (the subject says who it was for), so testing never mails a real
  candidate (N13).
"""

import logging
import os
import smtplib
import ssl
import time
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Annotated, Literal

import uvicorn
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("email-mcp")

SETTINGS = ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD")
NOT_SET_UP = "Email is not set up yet: add the SMTP_* settings to .env."
ADDRESS = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"  # one plain address, no names or lists

server = MCPServer(
    name="CandiVue email",
    instructions="Sends interview invitations to candidates by email.",
)


class Invite(BaseModel):
    """A calendar invite sent with the email (see make_ics)."""

    method: Literal["REQUEST", "CANCEL"]  # add/move, or remove
    uid: Annotated[str, Field(pattern=r"^[A-Za-z0-9.@_-]{3,200}$")]  # same event = same uid
    start: datetime
    end: datetime
    summary: Annotated[str, Field(min_length=2, max_length=200)]
    location: Annotated[str, Field(max_length=500)] = ""
    description: Annotated[str, Field(max_length=4000)] = ""


class SentEmail(BaseModel):
    """What a successful send returns: where it really went (the test
    recipient, if set) and the message id."""

    sent_to: str
    message_id: str


@server.tool()
def send_email(
    to: Annotated[str, Field(pattern=ADDRESS, max_length=255)],
    subject: Annotated[str, Field(min_length=2, max_length=200)],
    text: Annotated[str, Field(min_length=10, max_length=20_000)],
    html: Annotated[str, Field(max_length=100_000)] | None = None,
    invite: Invite | None = None,
) -> SentEmail:
    """Send one email to one address: plain text, plus an HTML version if
    given (email programs show the HTML one, or the text if they cannot),
    plus a calendar invite if given."""
    if not all(os.environ.get(name) for name in SETTINGS):
        raise ToolError(NOT_SET_UP)
    test_recipient = os.environ.get("EMAIL_TEST_RECIPIENT")
    message = EmailMessage()
    message["From"] = formataddr(
        (os.environ.get("EMAIL_FROM_NAME", "CandiVue"), os.environ["SMTP_USER"])
    )
    message["To"] = test_recipient or to
    message["Subject"] = f"[Test for {to}] {subject}" if test_recipient else subject
    message["Message-ID"] = make_msgid(domain="candivue.local")
    message.set_content(text)
    if html:
        message.add_alternative(html, subtype="html")
    if invite:
        ics = make_ics(invite, organizer=os.environ["SMTP_USER"], attendee=message["To"])
        message.add_attachment(
            ics.encode(),
            maintype="text",
            subtype="calendar",
            filename="invite.ics",
            params={"method": invite.method},
        )
    # ToolError = an expected failure whose message the caller may see; any
    # other error is hidden by MCP (no internal details leak).
    try:
        port = int(os.environ.get("SMTP_PORT", "465"))
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, context=context, timeout=30) as smtp:
            # Google shows app passwords in groups of four ("abcd efgh ...");
            # the spaces are not part of the password.
            password = os.environ["SMTP_PASSWORD"].replace(" ", "")
            smtp.login(os.environ["SMTP_USER"], password)
            smtp.send_message(message)
    except smtplib.SMTPAuthenticationError:
        logger.warning("Email sign-in failed")
        raise ToolError("The email sign-in failed: check SMTP_USER and the app password.") from None
    except smtplib.SMTPRecipientsRefused:
        logger.warning("Email address refused")
        raise ToolError("The email address was refused.") from None
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("Email could not be sent: %s", type(exc).__name__)
        raise ToolError("The email service could not be reached.") from None
    # No addresses in the log (personal data, N22).
    logger.info("Email sent%s", " (to the test recipient)" if test_recipient else "")
    return SentEmail(sent_to=message["To"], message_id=message["Message-ID"])


def make_ics(invite: Invite, organizer: str, attendee: str) -> str:
    """The invite as an iCalendar file (RFC 5545). SEQUENCE grows with every
    email (seconds since 1970), so the newest one wins in the calendar."""
    stamp = datetime.now(UTC)
    lines = [
        "BEGIN:VCALENDAR",
        "PRODID:-//CandiVue//Interviews//EN",
        "VERSION:2.0",
        "CALSCALE:GREGORIAN",
        f"METHOD:{invite.method}",
        "BEGIN:VEVENT",
        f"UID:{invite.uid}",
        f"DTSTAMP:{ics_time(stamp)}",
        f"SEQUENCE:{int(time.time())}",
        f"DTSTART:{ics_time(invite.start)}",
        f"DTEND:{ics_time(invite.end)}",
        f"SUMMARY:{ics_text(invite.summary)}",
        f"LOCATION:{ics_text(invite.location)}",
        f"DESCRIPTION:{ics_text(invite.description)}",
        f"ORGANIZER;CN={ics_text(os.environ.get('EMAIL_FROM_NAME', 'CandiVue'))}:mailto:{organizer}",
        f"ATTENDEE;ROLE=REQ-PARTICIPANT;PARTSTAT=NEEDS-ACTION;RSVP=FALSE:mailto:{attendee}",
        "STATUS:" + ("CANCELLED" if invite.method == "CANCEL" else "CONFIRMED"),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(fold(line) for line in lines) + "\r\n"


def ics_time(moment: datetime) -> str:
    """A time in UTC as iCalendar writes it: 20261020T040000Z."""
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def ics_text(text: str) -> str:
    """Escape text for iCalendar (backslash, ";", "," and line breaks)."""
    for char in ("\\", ";", ","):
        text = text.replace(char, "\\" + char)
    return text.replace("\r\n", "\n").replace("\n", "\\n")


def fold(line: str) -> str:
    """iCalendar lines are at most 75 characters: longer ones continue on
    the next line after a space."""
    parts = [line[i : i + 73] for i in range(0, len(line), 73)]
    return "\r\n ".join(parts)


# Only accept requests addressed to this service's Docker name (or local
# checks): protects against DNS-rebinding style tricks.
app = server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["email-mcp:*", "localhost:*", "127.0.0.1:*"],
    ),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8002)
