"""Sign in (interviewer), join by link (candidate), and "who am I"."""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import SESSION_EXPIRED, CurrentUser, get_current_user
from app.auth.security import (
    Role,
    create_access_token,
    hash_link_token,
    verify_password,
)
from app.db.database import get_db
from app.db.models import InterviewSession, User
from app.db.models.interview import SessionStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# Same message for an unknown email and a wrong password, so nobody can find
# out which emails have an account.
INVALID_LOGIN = "Email or password is incorrect."
LINK_NOT_RECOGNISED = (
    "This interview link was not recognised. Check the link in your invitation email."
)
INTERVIEW_OVER = "This interview has ended, so the link can no longer be used."


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=200)


class CandidateJoinRequest(BaseModel):
    link_token: str = Field(min_length=16, max_length=200)


class Me(BaseModel):
    """Who is signed in. Never contains scores or report data (N9)."""

    role: Role
    name: str | None = None  # interviewers only
    email: str | None = None  # interviewers only
    session_id: int | None = None  # candidates only: their interview


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Me


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Annotated[Session, Depends(get_db)]) -> TokenResponse:
    email = body.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))

    if not verify_password(body.password, user.password_hash if user else None):
        logger.info("Sign-in failed")  # no email in logs (N22)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID_LOGIN)

    logger.info("Sign-in: user %d", user.id)
    return TokenResponse(
        access_token=create_access_token(user.id, Role.INTERVIEWER),
        user=Me(role=Role.INTERVIEWER, name=user.full_name, email=user.email),
    )


@router.post("/candidate", response_model=TokenResponse)
def join_by_link(
    body: CandidateJoinRequest, db: Annotated[Session, Depends(get_db)]
) -> TokenResponse:
    """Swap the token from the invitation link for a candidate token that only
    works for that one interview."""
    interview = db.scalar(
        select(InterviewSession).where(
            InterviewSession.join_token_hash == hash_link_token(body.link_token)
        )
    )
    if interview is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, LINK_NOT_RECOGNISED)
    if interview.status in (SessionStatus.ENDED, SessionStatus.CANCELLED):
        raise HTTPException(status.HTTP_410_GONE, INTERVIEW_OVER)

    logger.info("Candidate joined by link: session %d", interview.id)
    return TokenResponse(
        access_token=create_access_token(interview.id, Role.CANDIDATE),
        user=Me(role=Role.CANDIDATE, session_id=interview.id),
    )


@router.get("/me", response_model=Me)
def me(
    user: Annotated[CurrentUser, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Me:
    if user.role == Role.CANDIDATE:
        return Me(role=Role.CANDIDATE, session_id=user.id)

    account = db.get(User, user.id)
    if account is None:  # account deleted after the token was issued
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, SESSION_EXPIRED)
    return Me(role=Role.INTERVIEWER, name=account.full_name, email=account.email)
