"""interview room

Waiting room (who is there, when the candidate was let in), the interview
questions made from the CV, and the chat between interviewer and candidate.

Revision ID: d7e2a9c41b58
Revises: c4d19e7a52f0
Create Date: 2026-10-13 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d7e2a9c41b58"
down_revision: str | None = "c4d19e7a52f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the waiting-room columns, cv_questions and interview_messages."""
    for column in ("interviewer_seen_at", "candidate_waiting_at", "admitted_at"):
        op.add_column(
            "interview_sessions",
            sa.Column(column, sa.DateTime(timezone=True), nullable=True),
        )
    op.add_column(
        "interview_sessions",
        sa.Column(
            "cv_questions", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )
    op.create_table(
        "interview_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column(
            "sender",
            sa.Enum(
                "interviewer",
                "candidate",
                name="speaker",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("text", sa.Text(), nullable=False),
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
            ["session_id"],
            ["interview_sessions.id"],
            name=op.f("fk_interview_messages_session_id_interview_sessions"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_interview_messages")),
    )
    op.create_index(
        op.f("ix_interview_messages_session_id_id"),
        "interview_messages",
        ["session_id", "id"],
    )


def downgrade() -> None:
    """Remove them again."""
    op.drop_index(
        op.f("ix_interview_messages_session_id_id"), table_name="interview_messages"
    )
    op.drop_table("interview_messages")
    op.drop_column("interview_sessions", "cv_questions")
    for column in ("admitted_at", "candidate_waiting_at", "interviewer_seen_at"):
        op.drop_column("interview_sessions", column)
