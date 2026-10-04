"""Database connection. The only module that knows how to reach PostgreSQL."""

import logging

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# The engine connects lazily: nothing happens until the first query.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,  # drop dead connections before using them
    connect_args={"connect_timeout": 3},  # fail fast if the database is down
)

# Opens a database session: `with SessionLocal() as db: ...`
SessionLocal = sessionmaker(engine)


def check_database() -> bool:
    """Return True if the database answers a trivial query."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except SQLAlchemyError as exc:
        # Log only the error type: the message can contain host and user names.
        logger.error("Database check failed: %s", type(exc).__name__)
        return False
