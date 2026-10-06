"""Shared base class and helpers for all database tables."""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Fixed names for keys and indexes, so Alembic migrations stay predictable.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """The parent class of every database table (with fixed key and index names)."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def include_name(name, type_, parent_names) -> bool:
    """Tell Alembic to ignore LangGraph's own checkpoint* tables.

    They are not in our models, so without this, autogenerate would try to
    drop them (and all saved workflow state with them).
    """
    if type_ == "table":
        return not name.startswith("checkpoint")
    return True


class TimestampMixin:
    """Adds created_at and updated_at, filled in by the database."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


def status_column(enum_class: type[StrEnum]) -> Enum:
    """Store a status as plain text (e.g. "approved").

    Python rejects values that are not in the enum before they reach the
    database. Plain text (not a PostgreSQL enum type) means adding a new
    status later does not need a migration.
    """
    return Enum(
        enum_class,
        native_enum=False,
        length=30,
        values_callable=lambda members: [member.value for member in members],
    )
