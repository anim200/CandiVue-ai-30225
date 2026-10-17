"""Talks to the job board through MCP (§4B-6): the only code that knows the
job board MCP server. Swapping Blogger for another board means changing that
server, not this module or the Hiring Assistant.

Each call tries up to 3 times (app/integrations/mcp_client.py); if it still
fails it raises JobBoardError with a message that is safe to show.
"""

from app.core.config import get_settings
from app.integrations.mcp_client import ToolFailed, call_tool


class JobBoardError(Exception):
    """The job board did not accept the post (message is safe to show)."""


def publish_job_post(title: str, html: str, labels: list[str]) -> dict:
    """Post the job and return {"post_id", "url"}; retry, then JobBoardError."""
    return _call("create_job_post", {"title": title, "html": html, "labels": labels})


def update_job_post(post_id: str, title: str, html: str) -> dict:
    """Replace an existing post's title and text; retry, then JobBoardError."""
    return _call("update_job_post", {"post_id": post_id, "title": title, "html": html})


def _call(tool: str, arguments: dict) -> dict:
    """Call a job board tool; a failure becomes JobBoardError."""
    try:
        return call_tool(get_settings().jobboard_mcp_url, tool, arguments)
    except ToolFailed as exc:
        raise JobBoardError(str(exc)) from None
