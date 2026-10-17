"""Calendar MCP server: called through a real MCP client (in memory), with a
fake Google session, so no real calendar is ever changed."""

import asyncio

import pytest
from mcp.client import Client

import server

START = "2026-10-20T10:00:00+06:00"
END = "2026-10-20T10:45:00+06:00"
EVENTS = "/calendars/primary/events"


class FakeResponse:
    """A pretend HTTP answer from Google Calendar."""

    def __init__(self, status_code, data=None):
        """Remember the status and body."""
        self.status_code = status_code
        self._data = data
        self.content = b"{}" if data is not None else b""

    def json(self):
        """Return the body."""
        return self._data


class FakeSession:
    """Records what would be sent to Google and answers with `response`."""

    def __init__(self, response):
        """Start with no recorded requests."""
        self.response = response
        self.sent = []

    def request(self, method, url, params=None, json=None, timeout=None):
        """Record the request and return the prepared answer."""
        self.sent.append((method, url, params, json))
        return self.response

    def get(self, url, **kwargs):
        """A GET request."""
        return self.request("get", url, **kwargs)

    def post(self, url, **kwargs):
        """A POST request."""
        return self.request("post", url, **kwargs)

    def patch(self, url, **kwargs):
        """A PATCH request."""
        return self.request("patch", url, **kwargs)

    def delete(self, url, **kwargs):
        """A DELETE request."""
        return self.request("delete", url, **kwargs)


def call_tool(tool, arguments):
    """Call a tool through an in-memory MCP client."""

    async def run():
        """Connect, call and return the result."""
        async with Client(server.server) as client:
            return await client.call_tool(tool, arguments)

    return asyncio.run(run())


@pytest.fixture
def calendar(monkeypatch):
    """A fake session that accepts every request."""
    monkeypatch.delenv("CALENDAR_ID", raising=False)
    session = FakeSession(
        FakeResponse(200, {"id": "abc123def", "htmlLink": "https://calendar.example/e"})
    )
    monkeypatch.setattr(server, "calendar_session", lambda: session)
    return session


def test_busy_times_skip_all_day_free_and_cancelled_events(calendar):
    timed = {"id": "busy1", "start": {"dateTime": START}, "end": {"dateTime": END}}
    calendar.response = FakeResponse(
        200,
        {
            "items": [
                timed,
                {"id": "allday", "start": {"date": "2026-10-20"}, "end": {"date": "2026-10-21"}},
                {**timed, "id": "free1", "transparency": "transparent"},
                {**timed, "id": "gone1", "status": "cancelled"},
            ]
        },
    )

    result = call_tool("list_busy", {"start": START, "end": END})

    assert not result.is_error
    busy = result.structured_content["busy"]
    assert [item["event_id"] for item in busy] == ["busy1"]
    method, url, params, _ = calendar.sent[0]
    assert method == "get" and url.endswith(EVENTS)
    assert "summary" not in params["fields"]  # titles are never fetched


def test_an_event_is_added_without_guests(calendar):
    result = call_tool(
        "create_event",
        {"summary": "Interview: Backend Developer", "start": START, "end": END},
    )

    assert not result.is_error
    assert result.structured_content == {
        "event_id": "abc123def",
        "url": "https://calendar.example/e",
    }
    method, url, _, body = calendar.sent[0]
    assert method == "post" and url.endswith(EVENTS)
    assert body["summary"] == "Interview: Backend Developer"
    assert "attendees" not in body


def test_an_event_is_moved(calendar):
    result = call_tool("move_event", {"event_id": "abc123def", "start": START, "end": END})

    assert not result.is_error
    method, url, _, body = calendar.sent[0]
    assert method == "patch" and url.endswith(EVENTS + "/abc123def")
    assert set(body) == {"start", "end"}


def test_deleting_an_event_that_is_already_gone_is_fine(calendar):
    calendar.response = FakeResponse(410)

    result = call_tool("delete_event", {"event_id": "abc123def"})

    assert not result.is_error
    assert calendar.sent[0][0] == "delete"


def test_event_ids_are_validated(calendar):
    result = call_tool("delete_event", {"event_id": "../other"})

    assert result.is_error
    assert calendar.sent == []  # nothing reached Google


def test_refused_request_gives_a_clear_error(calendar):
    calendar.response = FakeResponse(403)

    result = call_tool("list_busy", {"start": START, "end": END})

    assert result.is_error
    assert "refused the request (HTTP 403)" in result.content[0].text


def test_missing_settings_say_what_to_do(monkeypatch):
    for name in server.SETTINGS:
        monkeypatch.delenv(name, raising=False)

    result = call_tool("list_busy", {"start": START, "end": END})

    assert result.is_error
    assert "CALENDAR_" in result.content[0].text
