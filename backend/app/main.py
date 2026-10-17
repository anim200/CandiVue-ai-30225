"""Creates the FastAPI app. Start it with: uvicorn app.main:app"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    ai_models,
    analysis,
    assistant,
    auth,
    candidate,
    health,
    interviews,
    jobs,
    knowledge,
    livekit,
    rediscovery,
    screening,
)
from app.auth.seed import create_first_interviewer
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.db.database import SessionLocal
from app.graphs.checkpointer import open_checkpointer
from app.identity.references import purge_expired
from app.runs.runner import resume_interrupted_runs

settings = get_settings()
setup_logging(settings.log_level)
logger = logging.getLogger(__name__)

PURGE_EVERY_SECONDS = 3600


def purge_face_references() -> None:
    """Delete the face references whose time is up (F7 retention, N17)."""
    with SessionLocal() as db:
        purge_expired(db)


async def purge_face_references_hourly() -> None:
    """Run purge_face_references() now and then every hour."""
    while True:
        try:
            await asyncio.to_thread(purge_face_references)
        except Exception as error:  # noqa: BLE001 - try again next hour
            logger.warning("Face reference clean-up failed: %s", type(error).__name__)
        await asyncio.sleep(PURGE_EVERY_SECONDS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once at startup (before yield) and once at shutdown (after)."""
    # A fresh install gets its first interviewer account from .env (N21).
    with SessionLocal() as db:
        create_first_interviewer(db)

    with open_checkpointer() as checkpointer:
        # Every LangGraph in the app will use this to save its state.
        app.state.checkpointer = checkpointer
        # Continue AI runs that were interrupted by a stop or crash (N26).
        resume_interrupted_runs()
        purging = asyncio.create_task(purge_face_references_hourly())
        yield
        purging.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purging


app = FastAPI(
    title="CandiVue AI API",
    version="0.1.0",
    description="Backend for the CandiVue AI recruitment and interview platform.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(health.router)
app.include_router(auth.router)
app.include_router(knowledge.router)
app.include_router(jobs.router)
app.include_router(assistant.router)
app.include_router(ai_models.router)
app.include_router(screening.router)
app.include_router(interviews.router)
app.include_router(candidate.router)
app.include_router(livekit.router)
app.include_router(analysis.router)
app.include_router(rediscovery.router)
