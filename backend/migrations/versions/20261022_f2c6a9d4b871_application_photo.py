"""application photo as the F7 reference

§4B-15: the face photo sent with the application (Google Form) replaces the
reference taken from the camera before the interview, and the automatic
check during the call is removed. New: candidates.photo_file_id and
photo_consent, table application_photos. Removed: face_references and
interview_sessions.identity_recheck_at. Interviews that have not ended start
the check-in again (their old result belonged to the removed live check).

Revision ID: f2c6a9d4b871
Revises: e5b1c8d2f7a4
Create Date: 2026-10-22 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2c6a9d4b871"
down_revision: str | None = "e5b1c8d2f7a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _timestamps() -> list[sa.Column]:
    """created_at and updated_at, as every table has them."""
    return [
        sa.Column(
            name,
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        )
        for name in ("created_at", "updated_at")
    ]


def upgrade() -> None:
    """Add the application photo; remove the live-check reference."""
    op.add_column(
        "candidates", sa.Column("photo_file_id", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "candidates",
        sa.Column(
            "photo_consent", sa.Boolean(), server_default="false", nullable=False
        ),
    )
    op.create_table(
        "application_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ready",
                "no_face",
                "several_faces",
                "too_small",
                "unreadable",
                "too_large",
                "download_failed",
                name="photostatus",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("thumbnail", sa.LargeBinary(), nullable=True),
        sa.Column("tries", sa.Integer(), server_default="0", nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(
            ["candidate_id"],
            ["candidates.id"],
            name="fk_application_photos_candidate_id_candidates",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_application_photos"),
        sa.UniqueConstraint("candidate_id", name="uq_application_photos_candidate_id"),
    )
    op.drop_index("ix_face_references_candidate_id", table_name="face_references")
    op.drop_table("face_references")
    op.drop_column("interview_sessions", "identity_recheck_at")
    op.execute(
        "UPDATE interview_sessions SET identity_consent = NULL, "
        "identity_consent_at = NULL, identity_result = NULL "
        "WHERE status IN ('scheduled', 'live')"
    )


def downgrade() -> None:
    """Back to the live-check reference (application photos are lost)."""
    op.add_column(
        "interview_sessions",
        sa.Column("identity_recheck_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "face_references",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("candidate_id", sa.Integer(), nullable=False),
        sa.Column("embedding", sa.LargeBinary(), nullable=False),
        *_timestamps(),
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
    op.drop_table("application_photos")
    op.drop_column("candidates", "photo_consent")
    op.drop_column("candidates", "photo_file_id")
