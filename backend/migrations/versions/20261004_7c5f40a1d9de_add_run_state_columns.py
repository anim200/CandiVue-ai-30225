"""add run state columns

Revision ID: 7c5f40a1d9de
Revises: ebff38f92522
Create Date: 2026-10-04 16:04:22.277111
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c5f40a1d9de"
down_revision: str | None = "ebff38f92522"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUN_STATUS = sa.Enum(
    "pending",
    "running",
    "waiting_for_review",
    "completed",
    "failed",
    name="runstatus",
    native_enum=False,
    length=30,
)


def upgrade() -> None:
    # Reports that already exist were generated before this column existed,
    # so they count as completed (and are not re-run at startup).
    op.add_column(
        "assessment_reports",
        sa.Column("status", RUN_STATUS, nullable=False, server_default="completed"),
    )
    op.add_column("assessment_reports", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("assessment_reports", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.add_column("assessment_reports", sa.Column("error", sa.Text()))
    op.add_column("qa_analyses", sa.Column("started_at", sa.DateTime(timezone=True)))
    op.add_column("qa_analyses", sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.add_column(
        "screening_runs",
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("screening_runs", sa.Column("total", sa.Integer()))


def downgrade() -> None:
    op.drop_column("screening_runs", "total")
    op.drop_column("screening_runs", "processed")
    op.drop_column("qa_analyses", "finished_at")
    op.drop_column("qa_analyses", "started_at")
    op.drop_column("assessment_reports", "error")
    op.drop_column("assessment_reports", "finished_at")
    op.drop_column("assessment_reports", "started_at")
    op.drop_column("assessment_reports", "status")
