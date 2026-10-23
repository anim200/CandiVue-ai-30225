"""identity check and email access code

F7: the candidate's consent and face reference (encrypted embedding only),
the latest live identity result and re-check requests; the one-time email
code that must be entered before the interview link opens.

Revision ID: d4a9e7c3b512
Revises: c7e2a4f9d1b3
Create Date: 2026-10-18 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4a9e7c3b512"
down_revision: str | None = "c7e2a4f9d1b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSENT = sa.Enum(
    "given", "declined", name="identityconsent", native_enum=False, length=30
)
NEW_COLUMNS = (
    sa.Column("access_code_hash", sa.String(64), nullable=True),
    sa.Column("access_code_sent_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("access_code_expires_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("access_code_tries", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("identity_consent", CONSENT, nullable=True),
    sa.Column("identity_consent_at", sa.DateTime(timezone=True), nullable=True),
    sa.Column("identity_result", postgresql.JSONB(), nullable=True),
    sa.Column("identity_recheck_at", sa.DateTime(timezone=True), nullable=True),
)


def upgrade() -> None:
    """Add the session columns and the face_references table."""
    for column in NEW_COLUMNS:
        op.add_column("interview_sessions", column)
    op.create_table(
        "face_references",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
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
            name="fk_face_references_session_id_interview_sessions",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name="fk_face_references_candidate_id_candidates",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_face_references"),
        sa.UniqueConstraint("session_id", name="uq_face_references_session_id"),
    )
    op.create_index(
        "ix_face_references_candidate_id", "face_references", ["candidate_id"]
    )


def downgrade() -> None:
    """Remove the face_references table and the session columns."""
    op.drop_index("ix_face_references_candidate_id", table_name="face_references")
    op.drop_table("face_references")
    for column in reversed(NEW_COLUMNS):
        op.drop_column("interview_sessions", column.name)
