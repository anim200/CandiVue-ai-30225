"""Creates the FastAPI app. Start it with: uvicorn app.main:app"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai_models, assistant, auth, health, jobs, knowledge
from app.auth.seed import create_first_interviewer
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import setup_logging
from app.db.database import SessionLocal
from app.graphs.checkpointer import open_checkpointer
from app.runs.runner import resume_interrupted_runs

settings = get_settings()
setup_logging(settings.log_level)


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
        yield


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
