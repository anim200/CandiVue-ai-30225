"""Sends email through the email MCP server (§4B-4, §4B-6): the only code
that knows it. The email login lives only in that server's container."""

from app.core.config import get_settings
from app.integrations.mcp_client import ToolFailed, call_tool


class EmailError(Exception):
    """The email was not sent (message is safe to show)."""


def send_email(
    to: str,
    subject: str,
    text: str,
    html: str | None = None,
    invite: dict | None = None,
) -> dict:
    """Send one email (plain text, plus an HTML version and a calendar
    invite if given); returns {"sent_to", "message_id"}."""
    arguments = {"to": to, "subject": subject, "text": text, "html": html}
    if invite:
        arguments["invite"] = invite
    try:
        return call_tool(get_settings().email_mcp_url, "send_email", arguments)
    except ToolFailed as exc:
        raise EmailError(str(exc)) from None
