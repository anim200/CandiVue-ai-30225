"""Create the first interviewer account from .env, so a fresh install can sign
in without any manual step (N21). Runs at startup; does nothing once any
user exists, so changing .env later never overwrites an account."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.security import hash_password
from app.core.config import get_settings
from app.db.models import User

logger = logging.getLogger(__name__)

MIN_PASSWORD_LENGTH = 8


def create_first_interviewer(db: Session) -> None:
    """Create the first interviewer from .env if the database has no user yet."""
    settings = get_settings()
    email = (settings.demo_interviewer_email or "").strip().lower()
    password = settings.demo_interviewer_password

    if db.scalar(select(User.id).limit(1)) is not None:
        return  # accounts already exist
    if not email or password is None:
        logger.warning("No interviewer account: set DEMO_INTERVIEWER_* in .env")
        return
    if len(password.get_secret_value()) < MIN_PASSWORD_LENGTH:
        logger.warning(
            "No interviewer account: DEMO_INTERVIEWER_PASSWORD needs %d+ characters",
            MIN_PASSWORD_LENGTH,
        )
        return

    db.add(
        User(
            email=email,
            full_name=settings.demo_interviewer_name,
            password_hash=hash_password(password.get_secret_value()),
        )
    )
    db.commit()
    logger.info("Created the first interviewer account")
