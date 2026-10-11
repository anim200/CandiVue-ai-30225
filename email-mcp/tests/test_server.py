"""Email MCP server: called through a real MCP client (in memory), with a
fake SMTP server, so no real email is ever sent."""

import asyncio
import smtplib

import pytest
from mcp.client import Client

import server

TEXT = "Hello Candidate A, you are invited to an interview."


class FakeSmtp:
    """Stands in for smtplib.SMTP_SSL: records the login and the message."""

    sent = []
    fail = None  # an exception to raise on send

    def __init__(self, host, port, context, timeout):
        """Remember where it would connect."""
        self.address = (host, port)

    def __enter__(self):
        """Open the (fake) connection."""
        return self

    def __exit__(self, *args):
        """Close the (fake) connection."""

    def login(self, user, password):
        """Accept any login; remember the password that was used."""
        FakeSmtp.password = password

    def send_message(self, message):
        """Record the message, or fail like a real server would."""
        if FakeSmtp.fail:
            raise FakeSmtp.fail
        FakeSmtp.sent.append(message)


def call_tool(arguments):
    """Call send_email through an in-memory MCP client."""

    async def run():
        """Connect, call and return the result."""
        async with Client(server.server) as client:
            return await client.call_tool("send_email", arguments)

    return asyncio.run(run())


@pytest.fixture
def smtp(monkeypatch):
    """Email settings and the fake SMTP server."""
    for name, value in {
        "SMTP_HOST": "smtp.example.com",
        "SMTP_USER": "hiring@example.com",
        "SMTP_PASSWORD": "abcd efgh ijkl mnop",  # as Google shows it
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("EMAIL_TEST_RECIPIENT", raising=False)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSmtp)
    FakeSmtp.sent, FakeSmtp.fail = [], None
    return FakeSmtp


def test_an_email_is_sent_as_plain_text(smtp):
    result = call_tool(
        {"to": "candidate.a@example.com", "subject": "Interview invitation", "text": TEXT}
    )

    assert not result.is_error
    assert result.structured_content["sent_to"] == "candidate.a@example.com"
    (message,) = smtp.sent
    assert message["To"] == "candidate.a@example.com"
    assert message["Subject"] == "Interview invitation"
    assert message.get_content_type() == "text/plain"
    assert smtp.password == "abcdefghijklmnop"  # the spaces are not sent


def test_an_html_version_is_added_when_given(smtp):
    html = "<p>Hello Candidate A</p>"

    call_tool({"to": "a@example.com", "subject": "Interview", "text": TEXT, "html": html})

    (message,) = smtp.sent
    assert message.get_content_type() == "multipart/alternative"
    parts = [part.get_content_type() for part in message.iter_parts()]
    assert parts == ["text/plain", "text/html"]  # the text one is the fallback


def test_the_test_recipient_gets_every_email(smtp, monkeypatch):
    monkeypatch.setenv("EMAIL_TEST_RECIPIENT", "tester@example.com")

    result = call_tool(
        {"to": "candidate.a@example.com", "subject": "Interview invitation", "text": TEXT}
    )

    assert result.structured_content["sent_to"] == "tester@example.com"
    (message,) = smtp.sent
    assert message["To"] == "tester@example.com"
    assert message["Subject"] == "[Test for candidate.a@example.com] Interview invitation"


def test_a_refused_address_gives_a_clear_error(smtp):
    smtp.fail = smtplib.SMTPRecipientsRefused({})

    result = call_tool(
        {"to": "nobody@example.com", "subject": "Interview invitation", "text": TEXT}
    )

    assert result.is_error and "address was refused" in result.content[0].text


def test_missing_settings_say_what_to_do(monkeypatch):
    for name in server.SETTINGS:
        monkeypatch.delenv(name, raising=False)

    result = call_tool(
        {"to": "candidate.a@example.com", "subject": "Interview invitation", "text": TEXT}
    )

    assert result.is_error and "SMTP_" in result.content[0].text


@pytest.mark.parametrize("to", ["a@b.com, c@d.com", "Name <a@b.com>", "not-an-address"])
def test_only_one_plain_address_is_accepted(smtp, to):
    result = call_tool({"to": to, "subject": "Interview invitation", "text": TEXT})

    assert result.is_error and smtp.sent == []


INVITE = {
    "method": "REQUEST",
    "uid": "candivue-interview-7@candivue.local",
    "start": "2026-10-20T10:00:00+06:00",
    "end": "2026-10-20T10:45:00+06:00",
    "summary": "Interview: Backend Developer",
    "location": "https://candivue.example/join/abc",
    "description": "Join with your personal link; it is private, please keep it.",
}


def test_a_calendar_invite_is_attached(smtp, monkeypatch):
    monkeypatch.setenv("EMAIL_TEST_RECIPIENT", "tester@example.com")

    result = call_tool(
        {"to": "a@example.com", "subject": "Interview", "text": TEXT, "invite": INVITE}
    )

    assert not result.is_error
    (message,) = smtp.sent
    (invite,) = list(message.iter_attachments())
    assert invite.get_content_type() == "text/calendar"
    assert invite.get_param("method") == "REQUEST"
    ics = invite.get_content()
    lines = ics.split("\r\n")
    assert all(len(line) <= 75 for line in lines)
    unfolded = ics.replace("\r\n ", "")
    assert "UID:candivue-interview-7@candivue.local" in unfolded
    assert "DTSTART:20261020T040000Z" in unfolded  # stored in UTC
    assert r"DESCRIPTION:Join with your personal link\; it is private\, please" in unfolded
    assert "ORGANIZER;CN=CandiVue:mailto:hiring@example.com" in unfolded
    assert "mailto:tester@example.com" in unfolded  # whoever really gets it


def test_a_cancellation_removes_the_event(smtp):
    call_tool(
        {
            "to": "a@example.com",
            "subject": "Interview cancelled",
            "text": TEXT,
            "invite": {**INVITE, "method": "CANCEL"},
        }
    )

    (invite,) = list(smtp.sent[0].iter_attachments())
    ics = invite.get_content()
    assert "METHOD:CANCEL" in ics and "STATUS:CANCELLED" in ics
