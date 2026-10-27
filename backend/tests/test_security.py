"""Passwords and login tokens (no database needed)."""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.security import (
    InvalidTokenError,
    Role,
    create_access_token,
    hash_link_token,
    hash_password,
    read_access_token,
    verify_password,
)
from app.core.config import get_settings


def test_password_is_stored_as_a_hash_and_can_be_checked():
    stored = hash_password("correct horse battery")

    assert "correct horse battery" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong password", stored)


def test_unknown_user_never_matches():
    assert not verify_password("any password", None)


def test_token_round_trip():
    token = create_access_token(7, Role.INTERVIEWER)

    assert read_access_token(token) == (Role.INTERVIEWER, 7)


def test_expired_token_is_rejected():
    secret = get_settings().jwt_secret.get_secret_value()
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = jwt.encode(
        {"sub": "7", "role": "interviewer", "exp": past}, secret, "HS256"
    )

    with pytest.raises(InvalidTokenError):
        read_access_token(token)


def test_token_signed_with_another_secret_is_rejected():
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    forged = jwt.encode(
        {"sub": "7", "role": "interviewer", "exp": future},
        "someone-elses-secret-that-is-long-enough!!",
        "HS256",
    )

    with pytest.raises(InvalidTokenError):
        read_access_token(forged)


def test_token_with_unknown_role_is_rejected():
    secret = get_settings().jwt_secret.get_secret_value()
    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = jwt.encode({"sub": "7", "role": "admin", "exp": future}, secret, "HS256")

    with pytest.raises(InvalidTokenError):
        read_access_token(token)


def test_link_token_hash_is_fixed_length_and_hides_the_token():
    digest = hash_link_token("example-link-token-0123456789")

    assert len(digest) == 64
    assert "example-link-token" not in digest
    assert digest == hash_link_token("example-link-token-0123456789")
