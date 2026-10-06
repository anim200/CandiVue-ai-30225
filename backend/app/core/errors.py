"""Turn unexpected errors into a generic response.

The full error goes to the logs; the client never sees stack traces,
file paths or configuration (N12).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.ai.errors import AIServiceError

logger = logging.getLogger(__name__)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    """Log an unexpected error and answer with a generic 500 message."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


async def handle_ai_service_error(
    request: Request, exc: AIServiceError
) -> JSONResponse:
    """Answer 503 with a clear message when the AI service is unavailable."""
    # Already logged in invoke_llm(). 503 = temporary, the user can try again (N6).
    # Our own message (e.g. "model X reached its usage limit"), never prompt text.
    return JSONResponse(
        status_code=503,
        content={"detail": str(exc)},
    )


def register_error_handlers(app: FastAPI) -> None:
    """Connect the error handlers above to the FastAPI app."""
    app.add_exception_handler(AIServiceError, handle_ai_service_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
