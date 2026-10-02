"""Turn unexpected errors into a generic response.

The full error goes to the logs; the client never sees stack traces,
file paths or configuration (N12).
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Exception, handle_unexpected_error)
