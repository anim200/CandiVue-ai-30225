"""add llm models

The AI model the interviewer chose under the chat, and how many requests
each model used today (to show the free-tier quota).

Revision ID: 5b8e1f0c2d47
Revises: 9d41e6b2a7f3
Create Date: 2026-10-06 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5b8e1f0c2d47"
down_revision: str | None = "9d41e6b2a7f3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the llm_models table."""
    op.create_table(
        "llm_models",
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("usage_day", sa.Date(), nullable=True),
        sa.Column("requests_today", sa.Integer(), nullable=False),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("blocked_until", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("name", name=op.f("pk_llm_models")),
    )


def downgrade() -> None:
    """Remove the llm_models table."""
    op.drop_table("llm_models")
