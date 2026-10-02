"""Health check used by Docker and by humans to see if the backend is up."""

from typing import Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from app.db.database import check_database

router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "unavailable"]


@router.get("/health", response_model=HealthResponse)
def health(
    response: Response, database_ok: bool = Depends(check_database)
) -> HealthResponse:
    if database_ok:
        return HealthResponse(status="ok", database="ok")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return HealthResponse(status="degraded", database="unavailable")
