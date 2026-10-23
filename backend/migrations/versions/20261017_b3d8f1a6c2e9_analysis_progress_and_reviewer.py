"""analysis progress and reviewer

Q&A analyses count their evaluated units ("4 of 7"); assessment reports
remember which interviewer approved them or asked for changes.

Revision ID: b3d8f1a6c2e9
Revises: e4b8c2d19f73
Create Date: 2026-10-17 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3d8f1a6c2e9"
down_revision: str | None = "e4b8c2d19f73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add qa_analyses.processed/total and assessment_reports.reviewed_by_id."""
    op.add_column(
        "qa_analyses",
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("qa_analyses", sa.Column("total", sa.Integer(), nullable=True))
    op.add_column(
        "assessment_reports",
        sa.Column("reviewed_by_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_assessment_reports_reviewed_by_id_users",
        "assessment_reports",
        "users",
        ["reviewed_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    """Remove them again."""
    op.drop_constraint(
        "fk_assessment_reports_reviewed_by_id_users",
        "assessment_reports",
        type_="foreignkey",
    )
    op.drop_column("assessment_reports", "reviewed_by_id")
    op.drop_column("qa_analyses", "total")
    op.drop_column("qa_analyses", "processed")
