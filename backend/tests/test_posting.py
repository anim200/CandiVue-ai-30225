"""Posting an approved JD to the job board (no real MCP server or Blogger)."""

from datetime import UTC, datetime

import pytest

from app.assistant.posting import clean_form_url, render_post_html
from app.assistant.schemas import JobDescriptionContent, JobProfile
from app.integrations import mcp_client
from app.integrations.job_board import JobBoardError, publish_job_post
from app.integrations.mcp_client import ToolFailed

PROFILE = JobProfile.model_validate(
    {
        "title": "Python Backend Developer",
        "min_years_experience": 3,
        "requirements": [
            {"text": "FastAPI or Django", "level": "mandatory", "category": "skill"},
            {"text": "PostgreSQL", "level": "required", "category": "skill"},
            {"text": "Cloud", "level": "preferred", "category": "skill"},
        ],
    }
)
CONTENT = JobDescriptionContent(
    title="Python Backend Developer",
    about="Build services. <script>alert('x')</script> & more.",
    responsibilities=["Write <b>tested</b> code"],
    work_arrangement="Hybrid: 2 days at home.",
    what_we_offer=["Learning"],
    equal_opportunity="All qualified applicants are considered.",
)
FORM = "https://forms.gle/AbC123"


@pytest.mark.parametrize(
    "url",
    [
        "https://forms.gle/AbC123",
        "https://docs.google.com/forms/d/e/abc/viewform",
        "  https://forms.gle/AbC123  ",
    ],
)
def test_google_forms_links_are_accepted(url):
    assert clean_form_url(url) == url.strip()


@pytest.mark.parametrize(
    "url",
    [
        "http://forms.gle/AbC123",  # not https
        "https://docs.google.com/document/d/1",  # a Google Doc, not a form
        "https://evil.example.com/forms/x",
        "javascript:alert(1)",
    ],
)
def test_other_links_are_refused(url):
    with pytest.raises(ValueError, match="Google Forms"):
        clean_form_url(url)


def test_post_html_is_escaped_and_complete():
    body = render_post_html(CONTENT, PROFILE, FORM)

    assert "<script>" not in body and "&lt;script&gt;" in body
    assert "<b>tested</b>" not in body
    assert "3+ years of relevant experience" in body  # no experience requirement given
    assert "FastAPI or Django" in body and "PostgreSQL" in body
    assert "<h3>Nice to have</h3><ul><li>Cloud</li></ul>" in body
    assert f'href="{FORM}"' in body
    assert "synthetic" not in body.lower()  # a clean, professional post
    assert "Applications close" not in body  # no closing date set


def test_post_shows_the_closing_date_in_local_time():
    closes = datetime(2026, 10, 20, 11, 0, tzinfo=UTC)  # 17:00 in Dhaka

    body = render_post_html(CONTENT, PROFILE, FORM, closes)

    assert "<p>Applications close on Tue 20 Oct 2026, 17:00.</p>" in body


def test_publish_retries_then_succeeds(monkeypatch):
    calls = []

    async def flaky(url, tool, arguments):
        """Fail twice like a network hiccup, then succeed."""
        calls.append(tool)
        if len(calls) < 3:
            raise ConnectionError("network down")
        return {"post_id": "1", "url": "https://example.blogspot.com/p/1.html"}

    monkeypatch.setattr(mcp_client, "_call_once", flaky)
    monkeypatch.setattr(mcp_client, "WAIT_SECONDS", 0)

    assert publish_job_post("T", "<p>body text here</p>", [])["post_id"] == "1"
    assert len(calls) == 3


def test_a_server_that_is_not_set_up_is_asked_once(monkeypatch):
    calls = []

    async def not_set_up(url, tool, arguments):
        """The job board has no settings yet."""
        calls.append(tool)
        raise ToolFailed("The job board is not set up yet: add the BLOGGER_* settings.")

    monkeypatch.setattr(mcp_client, "_call_once", not_set_up)

    with pytest.raises(JobBoardError, match="not set up"):
        publish_job_post("T", "<p>body text here</p>", [])
    assert len(calls) == 1


def test_publish_gives_up_after_three_tries_with_a_safe_message(monkeypatch):
    async def refused(url, tool, arguments):
        """The job board refuses every time."""
        raise ToolFailed("The job board refused the post (HTTP 403).")

    monkeypatch.setattr(mcp_client, "_call_once", refused)
    monkeypatch.setattr(mcp_client, "WAIT_SECONDS", 0)

    with pytest.raises(JobBoardError, match="HTTP 403"):
        publish_job_post("T", "<p>body text here</p>", [])
