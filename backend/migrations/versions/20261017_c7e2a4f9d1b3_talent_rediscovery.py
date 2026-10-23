"""talent rediscovery

F11: candidates may agree to be considered for other vacancies
(open_to_other_roles), an application added from another job remembers
where it came from (rediscovered_from_id), and the talent-pool checks with
their matches are stored apart from screening runs.

Revision ID: c7e2a4f9d1b3
Revises: b3d8f1a6c2e9
Create Date: 2026-10-17 20:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c7e2a4f9d1b3"
down_revision: str | None = "b3d8f1a6c2e9"
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
    """Add the candidate columns and the two rediscovery tables."""
    op.add_column(
        "candidates",
        sa.Column(
            "open_to_other_roles", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "candidates", sa.Column("rediscovered_from_id", sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        "fk_candidates_rediscovered_from_id_candidates",
        "candidates",
        "candidates",
        ["rediscovered_from_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_table(
        "rediscovery_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("processed", sa.Integer(), nullable=False),
        sa.Column("total", sa.Integer(), nullable=True),
        sa.Column("status", RUN_STATUS, nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["jobs.id"],
            name="fk_rediscovery_runs_job_id_jobs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rediscovery_runs"),
    )
    op.create_index("ix_rediscovery_runs_job_id", "rediscovery_runs", ["job_id"])
    op.create_table(
        "rediscovery_matches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Float(), nullable=False),
        sa.Column(
            "dimension_scores", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column(
            "requirement_matches",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name="fk_rediscovery_matches_candidate_id_candidates",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["rediscovery_runs.id"],
            name="fk_rediscovery_matches_run_id_rediscovery_runs",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_rediscovery_matches"),
    )
    op.create_index("ix_rediscovery_matches_run_id", "rediscovery_matches", ["run_id"])
    op.create_index(
        "ix_rediscovery_matches_candidate_id", "rediscovery_matches", ["candidate_id"]
    )


def downgrade() -> None:
    """Remove them again."""
    op.drop_index("ix_rediscovery_matches_candidate_id", "rediscovery_matches")
    op.drop_index("ix_rediscovery_matches_run_id", "rediscovery_matches")
    op.drop_table("rediscovery_matches")
    op.drop_index("ix_rediscovery_runs_job_id", "rediscovery_runs")
    op.drop_table("rediscovery_runs")
    op.drop_constraint(
        "fk_candidates_rediscovered_from_id_candidates",
        "candidates",
        type_="foreignkey",
    )
    op.drop_column("candidates", "rediscovered_from_id")
    op.drop_column("candidates", "open_to_other_roles")
