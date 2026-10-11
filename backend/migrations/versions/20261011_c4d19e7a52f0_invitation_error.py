"""invitation error

Why the last invitation email failed (shown on the Interviews page).

Revision ID: c4d19e7a52f0
Revises: 8b2f47d913ac
Create Date: 2026-10-11 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4d19e7a52f0"
down_revision: str | None = "8b2f47d913ac"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add interview_sessions.invitation_error."""
    op.add_column(
        "interview_sessions",
        sa.Column("invitation_error", sa.String(300), nullable=True),
    )


def downgrade() -> None:
    """Remove it again."""
    op.drop_column("interview_sessions", "invitation_error")
