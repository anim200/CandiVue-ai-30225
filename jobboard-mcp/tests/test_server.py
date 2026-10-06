"""Job board MCP server: called through a real MCP client (in memory), with a
fake Blogger session, so no real post is ever made."""

import asyncio

import pytest
from mcp.client import Client

import server

HTML = "<h2>About the role</h2><p>Synthetic test job.</p>"


class FakeResponse:
    """A pretend HTTP answer from Blogger."""

    def __init__(self, status_code, data=None):
        """Remember the status and body."""
        self.status_code = status_code
        self._data = data or {}

    def json(self):
        """Return the body."""
        return self._data


class FakeSession:
    """Records what would be sent to Blogger and answers with `response`."""

    def __init__(self, response):
        """Start with no recorded requests."""
        self.response = response
        self.sent = []

    def post(self, url, json, timeout):
        """Record the request and return the prepared answer."""
        self.sent.append((url, json))
        return self.response


def call_tool(arguments):
    """Call create_job_post through an in-memory MCP client."""

    async def run():
        """Connect, call and return the result."""
        async with Client(server.server) as client:
            return await client.call_tool("create_job_post", arguments)

    return asyncio.run(run())


@pytest.fixture
def blog(monkeypatch):
    """Configured blog id and a fake session that accepts the post."""
    monkeypatch.setenv("BLOGGER_BLOG_ID", "123")
    session = FakeSession(
        FakeResponse(
            200, {"id": "999", "url": "https://example.blogspot.com/p/job.html"}
        )
    )
    monkeypatch.setattr(server, "blogger_session", lambda: session)
    return session


def test_post_is_published_and_its_address_returned(blog):
    result = call_tool(
        {"title": "Python Backend Developer", "html": HTML, "labels": ["Jobs"]}
    )

    assert not result.is_error
    assert result.structured_content == {
        "post_id": "999",
        "url": "https://example.blogspot.com/p/job.html",
    }
    url, body = blog.sent[0]
    assert url.endswith("/blogs/123/posts/")
    assert body["title"] == "Python Backend Developer" and body["content"] == HTML


def test_refused_post_gives_a_clear_error(blog):
    blog.response = FakeResponse(403)

    result = call_tool({"title": "Python Backend Developer", "html": HTML})

    assert result.is_error
    assert "refused the post (HTTP 403)" in result.content[0].text


def test_missing_settings_say_what_to_do(monkeypatch):
    for name in server.SETTINGS:
        monkeypatch.delenv(name, raising=False)

    result = call_tool({"title": "Python Backend Developer", "html": HTML})

    assert result.is_error
    assert "BLOGGER_" in result.content[0].text


def test_inputs_are_validated(blog):
    result = call_tool({"title": "x", "html": "short"})

    assert result.is_error
    assert blog.sent == []  # nothing reached Blogger
