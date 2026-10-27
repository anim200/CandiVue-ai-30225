"""Passwords and login tokens.

The only module that uses the two libraries (pwdlib for password hashing,
PyJWT for tokens), so either can be swapped without touching the rest.

A token is signed with JWT_SECRET and says who is calling:
- role "interviewer": "sub" is the user id (logged in with email + password)
- role "candidate":   "sub" is the interview session id (joined by link)
"""

import hashlib
from datetime import datetime, timedelta, timezone
from enum import StrEnum

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

ALGORITHM = "HS256"

# Argon2, the algorithm recommended for storing passwords today.
_password_hash = PasswordHash.recommended()

# Used when the email is unknown, so a wrong email takes as long to check as a
# wrong password. Otherwise the response time would reveal which emails exist.
_DUMMY_HASH = _password_hash.hash("not-a-real-password")


class Role(StrEnum):
    """The two roles in CandiVue: interviewer and candidate."""

    INTERVIEWER = "interviewer"
    CANDIDATE = "candidate"


class InvalidTokenError(Exception):
    """The token is missing a field, forged, or expired."""


def hash_password(password: str) -> str:
    """Turn a password into an Argon2 hash for storing (never store the password)."""
    return _password_hash.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """True if the password matches. Pass None when there is no such user."""
    if password_hash is None:
        _password_hash.verify(password, _DUMMY_HASH)  # same work, always False
        return False
    return _password_hash.verify(password, password_hash)


def hash_link_token(link_token: str) -> str:
    """Interview links are stored only as this SHA-256 hash (InterviewSession)."""
    return hashlib.sha256(link_token.encode()).hexdigest()


def create_access_token(subject: int, role: Role) -> str:
    """Create a signed login token that says who the user is and when it expires."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": str(subject),
        "role": role.value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_minutes),
    }
    return jwt.encode(claims, settings.jwt_secret.get_secret_value(), ALGORITHM)


def read_access_token(token: str) -> tuple[Role, int]:
    """Return (role, subject id) or raise InvalidTokenError."""
    secret = get_settings().jwt_secret.get_secret_value()
    try:
        claims = jwt.decode(
            token,
            secret,
            algorithms=[ALGORITHM],
            options={"require": ["exp", "sub", "role"]},
        )
        return Role(claims["role"]), int(claims["sub"])
    except (jwt.InvalidTokenError, ValueError) as exc:
        raise InvalidTokenError from exc
