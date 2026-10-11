"""shortlist and interview length

When a candidate was shortlisted (only shortlisted candidates can be
invited) and how long each interview is.

Revision ID: 8b2f47d913ac
Revises: 3e8a61c0b5d2
Create Date: 2026-10-11 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8b2f47d913ac"
down_revision: str | None = "3e8a61c0b5d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add candidates.shortlisted_at and interview_sessions.duration_minutes."""
    op.add_column(
        "candidates",
        sa.Column("shortlisted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "interview_sessions",
        sa.Column(
            "duration_minutes", sa.Integer(), nullable=False, server_default="45"
        ),
    )


def downgrade() -> None:
    """Remove them again."""
    op.drop_column("interview_sessions", "duration_minutes")
    op.drop_column("candidates", "shortlisted_at")
