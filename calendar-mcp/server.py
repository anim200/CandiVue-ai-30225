"""Calendar MCP server: the interviewer's Google Calendar (§4B-8).

The Hiring Assistant (LangGraph 1) uses it through MCP to check busy times
before it suggests or confirms interview times, and, after the interviewer
confirmed, to add, move or delete the interview events. Events go on the
interviewer's own calendar only: candidates are never added as guests, so
Google never emails them (they get an "Add to calendar" file by email).
Only this container holds the Google sign-in, so the backend never sees it
(least privilege). It has no port on the host.

Settings (environment / .env):
  CALENDAR_CLIENT_ID, CALENDAR_CLIENT_SECRET, CALENDAR_REFRESH_TOKEN
  (one-time sign-in, see get_refresh_token.py), CALENDAR_ID (default:
  "primary", the account's main calendar).
"""

import logging
import os
from datetime import datetime
from typing import Annotated

import requests
import uvicorn
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import AuthorizedSession
from google.oauth2.credentials import Credentials
from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
logger = logging.getLogger("calendar-mcp")

CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.events"
TOKEN_URI = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/{calendar}/events"
SETTINGS = ("CALENDAR_CLIENT_ID", "CALENDAR_CLIENT_SECRET", "CALENDAR_REFRESH_TOKEN")
NOT_SET_UP = "The calendar is not set up yet: add the CALENDAR_* settings to .env."
EVENT_ID = r"^[a-v0-9]{5,1024}$"  # Google's event id alphabet (base32hex)

server = MCPServer(
    name="CandiVue calendar",
    instructions="Checks the interviewer's busy times and keeps interview events.",
)


class BusyTime(BaseModel):
    """One busy period (no title or details: only the times are needed)."""

    event_id: str
    start: datetime
    end: datetime


class Busy(BaseModel):
    """The busy periods between two times."""

    busy: list[BusyTime]


class Event(BaseModel):
    """An event in the calendar: its id and its page in Google Calendar."""

    event_id: str
    url: str


@server.tool()
def list_busy(start: datetime, end: datetime) -> Busy:
    """Busy periods in the calendar between start and end (with time zones).
    All-day events and events marked "free" do not count."""
    params = {
        "timeMin": start.isoformat(),
        "timeMax": end.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "2500",  # Google's largest page
        "fields": "items(id,start,end,transparency,status)",
    }
    items = call_google("get", "", params=params).get("items", [])
    return Busy(
        busy=[
            BusyTime(
                event_id=item["id"],
                start=item["start"]["dateTime"],
                end=item["end"]["dateTime"],
            )
            for item in items
            if "dateTime" in item.get("start", {})  # not all-day
            and item.get("transparency") != "transparent"
            and item.get("status") != "cancelled"
        ]
    )


@server.tool()
def create_event(
    summary: Annotated[str, Field(min_length=2, max_length=200)],
    start: datetime,
    end: datetime,
    description: Annotated[str, Field(max_length=4000)] = "",
    location: Annotated[str, Field(max_length=500)] = "",
) -> Event:
    """Add an event (an interview) to the calendar, with no guests."""
    body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start.isoformat()},
        "end": {"dateTime": end.isoformat()},
    }
    data = call_google("post", "", body=body)
    logger.info("Event added: %s", data.get("id"))
    return Event(event_id=data["id"], url=data.get("htmlLink", ""))


@server.tool()
def move_event(
    event_id: Annotated[str, Field(pattern=EVENT_ID)], start: datetime, end: datetime
) -> Event:
    """Move an event to a new start and end time."""
    body = {"start": {"dateTime": start.isoformat()}, "end": {"dateTime": end.isoformat()}}
    data = call_google("patch", event_id, body=body)
    logger.info("Event moved: %s", event_id)
    return Event(event_id=data["id"], url=data.get("htmlLink", ""))


@server.tool()
def delete_event(event_id: Annotated[str, Field(pattern=EVENT_ID)]) -> Event:
    """Delete an event (a cancelled interview)."""
    call_google("delete", event_id)
    logger.info("Event deleted: %s", event_id)
    return Event(event_id=event_id, url="")


def calendar_session() -> AuthorizedSession:
    """An HTTP session signed in to Google Calendar with the refresh token
    (google-auth gets a fresh access token by itself)."""
    if not all(os.environ.get(name) for name in SETTINGS):
        raise ToolError(NOT_SET_UP)
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["CALENDAR_REFRESH_TOKEN"],
        client_id=os.environ["CALENDAR_CLIENT_ID"],
        client_secret=os.environ["CALENDAR_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=[CALENDAR_SCOPE],
    )
    return AuthorizedSession(credentials)


def call_google(method: str, event_id: str, params=None, body=None) -> dict:
    """Send one request to Google Calendar (method get/post/patch/delete, on
    the event list or one event) and return its answer; any failure becomes
    a safe ToolError (no internal details leak)."""
    session = calendar_session()
    calendar = os.environ.get("CALENDAR_ID", "primary")
    url = EVENTS_URL.format(calendar=calendar) + (f"/{event_id}" if event_id else "")
    try:
        response = getattr(session, method)(url, params=params, json=body, timeout=30)
    except GoogleAuthError as exc:
        logger.warning("Calendar sign-in failed: %s", type(exc).__name__)
        raise ToolError("The calendar sign-in failed: create a new refresh token.") from None
    except requests.RequestException as exc:
        logger.warning("Calendar could not be reached: %s", type(exc).__name__)
        raise ToolError("The calendar could not be reached.") from None
    if method == "delete" and response.status_code in (404, 410):
        return {}  # already gone: nothing to do
    if response.status_code >= 400:
        # Status only: the body could echo the request.
        logger.warning("Calendar refused the request: HTTP %d", response.status_code)
        raise ToolError(f"The calendar refused the request (HTTP {response.status_code}).")
    return response.json() if response.content else {}


# Only accept requests addressed to this service's Docker name (or local
# checks): protects against DNS-rebinding style tricks.
app = server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["calendar-mcp:*", "localhost:*", "127.0.0.1:*"],
    ),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
