"""screening weights and cv passages

Scoring weights on the job (the interviewer's and the AI suggestion), the
weights each screening run used, and the CV passages with embeddings that
screening compares with the job requirements.

Revision ID: 7a3c9d2e4f61
Revises: 5b8e1f0c2d47
Create Date: 2026-10-08 10:00:00
"""

from collections.abc import Sequence

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7a3c9d2e4f61"
down_revision: str | None = "5b8e1f0c2d47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the weight columns and the cv_passages table."""
    op.add_column(
        "jobs",
        sa.Column("weights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "jobs",
        sa.Column("ai_weights", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "screening_runs",
        sa.Column(
            "weights",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.create_table(
        "cv_passages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=30), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "embedding", pgvector.sqlalchemy.vector.VECTOR(dim=1024), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name=op.f("fk_cv_passages_candidate_id_candidates"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cv_passages")),
    )
    op.create_index(
        op.f("ix_cv_passages_candidate_id"), "cv_passages", ["candidate_id"]
    )


def downgrade() -> None:
    """Remove the cv_passages table and the weight columns."""
    op.drop_index(op.f("ix_cv_passages_candidate_id"), table_name="cv_passages")
    op.drop_table("cv_passages")
    op.drop_column("screening_runs", "weights")
    op.drop_column("jobs", "ai_weights")
    op.drop_column("jobs", "weights")
