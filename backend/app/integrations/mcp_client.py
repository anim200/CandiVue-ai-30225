"""Calls a tool on one of CandiVue's MCP servers (job board, email,
calendar), trying up to 3 times with a short, growing pause. If it still
fails, ToolFailed carries a message that is safe to show. A server that is
"not set up" (missing settings) is not asked again: that cannot change."""

import asyncio
import logging
import time

from mcp.client import Client

logger = logging.getLogger(__name__)

ATTEMPTS = 3  # design: "I tried 3 times"
WAIT_SECONDS = 1.0  # pause before the 2nd try, doubled before the 3rd; tests set 0
NOT_SET_UP = "not set up"  # in the servers' message for missing settings


class ToolFailed(Exception):
    """The MCP server did not do it (the message is safe to show)."""


async def _call_once(url: str, tool: str, arguments: dict) -> dict:
    """Connect to the MCP server, call the tool once and return its result."""
    async with Client(url) as client:
        result = await client.call_tool(tool, arguments)
    if result.is_error:
        message = result.content[0].text if result.content else ""
        # MCP adds "Error executing tool <name>: "; keep only the plain message.
        message = (
            message.split(": ", 1)[-1]
            if message.startswith("Error executing tool")
            else message
        )
        raise ToolFailed(message or "The service refused the request.")
    return result.structured_content


def call_tool(url: str, tool: str, arguments: dict) -> dict:
    """Call the tool, trying up to ATTEMPTS times; then raise ToolFailed."""
    last_error = "The service could not be reached."
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return asyncio.run(_call_once(url, tool, arguments))
        except ToolFailed as exc:
            last_error = str(exc)
            if NOT_SET_UP in last_error:
                break
        except Exception as exc:  # noqa: BLE001 - network/MCP errors: retry, then a safe message
            logger.warning("MCP call %s failed: %s", tool, type(exc).__name__)
        if attempt < ATTEMPTS:
            time.sleep(WAIT_SECONDS * 2 ** (attempt - 1))
    raise ToolFailed(last_error)
