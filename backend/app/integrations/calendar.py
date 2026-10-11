"""The interviewer's Google Calendar, through the calendar MCP server
(§4B-8): the only code that knows it. The Google sign-in lives only in that
server's container."""

from datetime import datetime

from app.core.config import get_settings
from app.integrations.mcp_client import ToolFailed, call_tool


class CalendarError(Exception):
    """The calendar did not answer or refused (message is safe to show)."""


def busy(start: datetime, end: datetime) -> list[dict]:
    """Busy periods between start and end: [{"event_id", "start", "end"}]
    (times as ISO text; no titles)."""
    found = _call("list_busy", {"start": start.isoformat(), "end": end.isoformat()})
    return found["busy"]


def add_event(summary: str, start: datetime, end: datetime, description: str) -> str:
    """Add an event (no guests); returns its id."""
    arguments = {
        "summary": summary,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "description": description,
    }
    return _call("create_event", arguments)["event_id"]


def move_event(event_id: str, start: datetime, end: datetime) -> None:
    """Move an event to a new time."""
    arguments = {
        "event_id": event_id,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    _call("move_event", arguments)


def delete_event(event_id: str) -> None:
    """Delete an event (fine if it is already gone)."""
    _call("delete_event", {"event_id": event_id})


def _call(tool: str, arguments: dict) -> dict:
    """Call a calendar tool; failures become CalendarError."""
    try:
        return call_tool(get_settings().calendar_mcp_url, tool, arguments)
    except ToolFailed as exc:
        raise CalendarError(str(exc)) from None
