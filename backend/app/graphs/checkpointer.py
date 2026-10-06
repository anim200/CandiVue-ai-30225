"""Saves LangGraph state in PostgreSQL so a workflow resumes after a restart (N26).

After every step, LangGraph writes the graph state (a "checkpoint") under the
run's thread_id. Running the same thread_id again continues from the last
saved step instead of starting over. Human-review pauses are saved the same way.
"""

from collections.abc import Generator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool
from sqlalchemy.engine import make_url

from app.core.config import get_settings


def _postgres_conninfo() -> str:
    """Turn the SQLAlchemy URL (postgresql+psycopg://...) into a plain one."""
    url = make_url(get_settings().database_url).set(drivername="postgresql")
    return url.render_as_string(hide_password=False)


@contextmanager
def open_checkpointer() -> Generator[PostgresSaver]:
    """Open a connection pool and yield a ready checkpointer; close on exit."""
    with ConnectionPool(
        _postgres_conninfo(),
        max_size=5,
        # Settings the PostgreSQL checkpointer needs.
        kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
    ) as pool:
        checkpointer = PostgresSaver(pool)
        # Creates LangGraph's own checkpoint tables if missing. LangGraph
        # manages these tables itself, so they are not in our Alembic models.
        checkpointer.setup()
        yield checkpointer
