"""Email MCP server: sends interview invitations by email (§4B-4, §4B-6).

The Hiring Assistant (LangGraph 1) calls this server's single tool,
send_email, through MCP after the interviewer confirmed the interviews.
Only this container holds the email login, so the backend never sees it
(least privilege). It has no port on the host: only other containers in
Docker's network can reach it. Emails are plain text, so they cannot carry
code.

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
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from typing import Annotated

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
) -> SentEmail:
    """Send one plain-text email to one address."""
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
    # ToolError = an expected failure whose message the caller may see; any
    # other error is hidden by MCP (no internal details leak).
    try:
        port = int(os.environ.get("SMTP_PORT", "465"))
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(os.environ["SMTP_HOST"], port, context=context, timeout=30) as smtp:
            smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASSWORD"])
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
