"""Who is calling, and may they use this route? (N9)

Use in routes:
    Depends(require_interviewer)  - jobs, scores, rankings, reports ... (most routes)
    Depends(require_candidate)    - the candidate's own interview only
Every interviewer router adds require_interviewer; tests/test_auth_routes.py
fails if an /api route forgets its guard.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.security import InvalidTokenError, Role, read_access_token

# Reads "Authorization: Bearer <token>". auto_error=False: we send our own
# plain-language message instead of FastAPI's default.
_bearer = HTTPBearer(auto_error=False)

NOT_SIGNED_IN = "Please sign in to continue."
SESSION_EXPIRED = "Your session has expired. Please sign in again."
INTERVIEWERS_ONLY = "This is only available to interviewers."
CANDIDATES_ONLY = "This is only available to the invited candidate."


@dataclass
class CurrentUser:
    role: Role
    id: int  # user id for an interviewer, interview session id for a candidate


def _unauthorized(message: str) -> HTTPException:
    return HTTPException(
        status.HTTP_401_UNAUTHORIZED, message, headers={"WWW-Authenticate": "Bearer"}
    )


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> CurrentUser:
    """401 if there is no token or it is invalid/expired."""
    if credentials is None:
        raise _unauthorized(NOT_SIGNED_IN)
    try:
        role, subject_id = read_access_token(credentials.credentials)
    except InvalidTokenError:
        raise _unauthorized(SESSION_EXPIRED) from None
    return CurrentUser(role=role, id=subject_id)


def require_interviewer(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    """403 for candidates: they never see scores, rankings or reports (N9)."""
    if user.role != Role.INTERVIEWER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, INTERVIEWERS_ONLY)
    return user


def require_candidate(
    user: Annotated[CurrentUser, Depends(get_current_user)],
) -> CurrentUser:
    if user.role != Role.CANDIDATE:
        raise HTTPException(status.HTTP_403_FORBIDDEN, CANDIDATES_ONLY)
    return user
