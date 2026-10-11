"""Talks to the job board through MCP (§4B-6): the only code that knows the
job board MCP server. Swapping Blogger for another board means changing that
server, not this module or the Hiring Assistant.

publish_job_post() and update_job_post() try up to 3 times with a short,
growing pause; if it still fails they raise JobBoardError with a message
that is safe to show.
"""

import asyncio
import logging
import time

from mcp.client import Client

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ATTEMPTS = 3  # design: "I tried 3 times"
WAIT_SECONDS = 1.0  # pause before the 2nd try, doubled before the 3rd; tests set 0


class JobBoardError(Exception):
    """The job board did not accept the post (message is safe to show)."""


async def _call_once(tool: str, arguments: dict) -> dict:
    """Connect to the MCP server, call the tool once and return its result."""
    async with Client(get_settings().jobboard_mcp_url) as client:
        result = await client.call_tool(tool, arguments)
    if result.is_error:
        message = result.content[0].text if result.content else ""
        # MCP adds "Error executing tool <name>: "; keep only the plain message.
        message = (
            message.split(": ", 1)[-1]
            if message.startswith("Error executing tool")
            else message
        )
        raise JobBoardError(message or "The job board refused the post.")
    return result.structured_content


def publish_job_post(title: str, html: str, labels: list[str]) -> dict:
    """Post the job and return {"post_id", "url"}; retry, then JobBoardError."""
    return _call("create_job_post", {"title": title, "html": html, "labels": labels})


def update_job_post(post_id: str, title: str, html: str) -> dict:
    """Replace an existing post's title and text; retry, then JobBoardError."""
    return _call("update_job_post", {"post_id": post_id, "title": title, "html": html})


def _call(tool: str, arguments: dict) -> dict:
    """Call a job board tool, trying up to ATTEMPTS times."""
    last_error = "The job board could not be reached."
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return asyncio.run(_call_once(tool, arguments))
        except JobBoardError as exc:
            last_error = str(exc)
        except Exception as exc:  # noqa: BLE001 - network/MCP errors: retry, then a safe message
            logger.warning("Job board call failed: %s", type(exc).__name__)
        if attempt < ATTEMPTS:
            time.sleep(WAIT_SECONDS * 2 ** (attempt - 1))
    raise JobBoardError(last_error)
