"""Job board MCP server: posts an approved job description to a Blogger blog.

The Hiring Assistant (LangGraph 1) calls this server's tool create_job_post
through MCP after the interviewer approved the JD (§4B-2, §4B-6), and
update_job_post when the post must change (a new closing date). Only this container holds the Blogger credentials, so the backend
never sees them (least privilege). It has no port on the host: only other
containers in Docker's network can reach it.

Settings (environment / .env):
  BLOGGER_CLIENT_ID, BLOGGER_CLIENT_SECRET, BLOGGER_REFRESH_TOKEN  (one-time
  sign-in, see get_refresh_token.py), BLOGGER_BLOG_ID (the private blog).
"""

import logging
import os
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
logger = logging.getLogger("jobboard-mcp")

BLOGGER_SCOPE = "https://www.googleapis.com/auth/blogger"
TOKEN_URI = "https://oauth2.googleapis.com/token"
POSTS_URL = "https://www.googleapis.com/blogger/v3/blogs/{blog_id}/posts/"
SETTINGS = (
    "BLOGGER_CLIENT_ID",
    "BLOGGER_CLIENT_SECRET",
    "BLOGGER_REFRESH_TOKEN",
    "BLOGGER_BLOG_ID",
)
NOT_SET_UP = "The job board is not set up yet: add the BLOGGER_* settings to .env."

server = MCPServer(
    name="CandiVue job board",
    instructions="Posts approved job descriptions to the company's job board.",
)


class JobPost(BaseModel):
    """What a successful post returns: its id and public address."""

    post_id: str
    url: str


def blogger_session() -> AuthorizedSession:
    """A signed-in HTTP session for Blogger, made from the refresh token.

    Google's library swaps the long-lived refresh token for a short-lived
    access token on the first request and renews it when it expires.
    """
    if not all(os.environ.get(name) for name in SETTINGS):
        raise ToolError(NOT_SET_UP)
    credentials = Credentials(
        token=None,
        refresh_token=os.environ["BLOGGER_REFRESH_TOKEN"],
        client_id=os.environ["BLOGGER_CLIENT_ID"],
        client_secret=os.environ["BLOGGER_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=[BLOGGER_SCOPE],
    )
    return AuthorizedSession(credentials)


@server.tool()
def create_job_post(
    title: Annotated[str, Field(min_length=2, max_length=200)],
    html: Annotated[str, Field(min_length=20, max_length=100_000)],
    labels: Annotated[list[str], Field(max_length=5)] = [],  # noqa: B006 (copied by pydantic)
) -> JobPost:
    """Publish a job post (title + HTML body) on the job board blog and
    return its address. The HTML is prepared and escaped by the backend."""
    body = {"kind": "blogger#post", "title": title, "content": html, "labels": labels}
    data = send_to_blogger("post", "", body)
    logger.info("Job post published: %s", data.get("id"))
    return JobPost(post_id=str(data["id"]), url=data["url"])


@server.tool()
def update_job_post(
    post_id: Annotated[str, Field(pattern=r"^\d{1,30}$")],
    title: Annotated[str, Field(min_length=2, max_length=200)],
    html: Annotated[str, Field(min_length=20, max_length=100_000)],
) -> JobPost:
    """Replace the title and HTML body of an existing job post (e.g. after the
    closing date changed). Its address stays the same."""
    data = send_to_blogger("patch", post_id, {"title": title, "content": html})
    logger.info("Job post updated: %s", post_id)
    return JobPost(post_id=str(data["id"]), url=data["url"])


def send_to_blogger(method: str, post_id: str, body: dict) -> dict:
    """Send one request to Blogger ("post" = new post, "patch" = change
    post_id) and return its answer; any failure becomes a safe ToolError."""
    session = blogger_session()
    url = POSTS_URL.format(blog_id=os.environ["BLOGGER_BLOG_ID"]) + post_id
    # ToolError = an expected failure whose message the caller may see; any
    # other error is hidden by MCP (no internal details leak).
    try:
        response = getattr(session, method)(url, json=body, timeout=30)
    except GoogleAuthError as exc:
        logger.warning("Blogger sign-in failed: %s", type(exc).__name__)
        raise ToolError(
            "The job board sign-in failed: create a new refresh token."
        ) from None
    except requests.RequestException as exc:
        logger.warning("Blogger could not be reached: %s", type(exc).__name__)
        raise ToolError("The job board could not be reached.") from None
    if response.status_code >= 400:
        # Status only: the body could echo the request.
        logger.warning("Blogger refused the post: HTTP %d", response.status_code)
        raise ToolError(
            f"The job board refused the post (HTTP {response.status_code})."
        )
    return response.json()


# Only accept requests addressed to this service's Docker name (or local
# checks): protects against DNS-rebinding style tricks.
app = server.streamable_http_app(
    streamable_http_path="/mcp",
    stateless_http=True,
    host="0.0.0.0",
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["jobboard-mcp:*", "localhost:*", "127.0.0.1:*"],
    ),
)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)
