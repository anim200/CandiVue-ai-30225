"""AI model API: list the models the interviewer can choose and pick one.

Interviewers only (N9). Only models on the allowed list (LLM_MODELS in .env)
can be chosen. The usage numbers are counted by CandiVue; Google's own
numbers are on its usage page (usage_url).
"""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.ai.usage import USAGE_URL, choose_model, model_overview
from app.auth.dependencies import require_interviewer
from app.db.database import get_db

router = APIRouter(
    prefix="/api/ai", tags=["ai models"], dependencies=[Depends(require_interviewer)]
)


class ModelOut(BaseModel):
    """One model in the picker, with what we know about its quota today."""

    name: str
    selected: bool
    requests_today: int  # counted by CandiVue
    daily_limit: int | None  # from Google's "limit reached" answer, if seen
    blocked_until: datetime | None  # limit reached: usable again after this


class ModelsOut(BaseModel):
    """All allowed models and the link to Google's usage page."""

    models: list[ModelOut]
    usage_url: str


class ChooseModelRequest(BaseModel):
    """The model to use for every AI call from now on."""

    name: str = Field(min_length=1, max_length=100)


@router.get("/models", response_model=ModelsOut)
def list_models(db: Annotated[Session, Depends(get_db)]) -> ModelsOut:
    """List the allowed models, the chosen one and today's usage."""
    return ModelsOut(models=model_overview(db), usage_url=USAGE_URL)


@router.put("/model", response_model=ModelsOut)
def set_model(
    body: ChooseModelRequest, db: Annotated[Session, Depends(get_db)]
) -> ModelsOut:
    """Choose the model for every AI call (allowed models only)."""
    try:
        choose_model(db, body.name)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None
    return ModelsOut(models=model_overview(db), usage_url=USAGE_URL)
