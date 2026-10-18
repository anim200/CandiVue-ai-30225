"""candidate selected (selection email sent)

§4B-14: when the selection email is sent after the approved assessment
report, the candidate is marked as selected.

Revision ID: e5b1c8d2f7a4
Revises: d4a9e7c3b512
Create Date: 2026-10-18 15:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b1c8d2f7a4"
down_revision: str | None = "d4a9e7c3b512"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add candidates.selected_at."""
    op.add_column(
        "candidates",
        sa.Column("selected_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Remove candidates.selected_at."""
    op.drop_column("candidates", "selected_at")
