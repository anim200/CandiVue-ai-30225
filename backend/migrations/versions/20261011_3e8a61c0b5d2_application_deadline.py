"""application deadline

The date applications close (CVs after it are not collected; invitations
wait for it) and the job board's post id, so the post can be updated.

Revision ID: 3e8a61c0b5d2
Revises: 7a3c9d2e4f61
Create Date: 2026-10-11 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e8a61c0b5d2"
down_revision: str | None = "7a3c9d2e4f61"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two job columns."""
    op.add_column(
        "jobs",
        sa.Column("applications_close_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "jobs", sa.Column("job_board_post_id", sa.String(length=200), nullable=True)
    )


def downgrade() -> None:
    """Remove them again."""
    op.drop_column("jobs", "job_board_post_id")
    op.drop_column("jobs", "applications_close_at")
