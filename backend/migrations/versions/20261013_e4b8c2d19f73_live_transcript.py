"""live transcript

The transcriber's heartbeat and its last problem on each interview, so the
room can show "Listening" or why speech-to-text is not working.

Revision ID: e4b8c2d19f73
Revises: d7e2a9c41b58
Create Date: 2026-10-13 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b8c2d19f73"
down_revision: str | None = "d7e2a9c41b58"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add transcriber_seen_at and transcript_problem."""
    op.add_column(
        "interview_sessions",
        sa.Column("transcriber_seen_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column("transcript_problem", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    """Remove them again."""
    op.drop_column("interview_sessions", "transcript_problem")
    op.drop_column("interview_sessions", "transcriber_seen_at")
