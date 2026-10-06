"""Runs migrations against the app database (connection from app.db.database)."""

from logging.config import fileConfig

from alembic import context

import app.db.models  # noqa: F401  (registers every table on Base.metadata)
from app.db.base import Base, include_name
from app.db.database import engine

if context.config.config_file_name is not None:
    fileConfig(context.config.config_file_name)

with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        include_name=include_name,
    )
    with context.begin_transaction():
        context.run_migrations()
