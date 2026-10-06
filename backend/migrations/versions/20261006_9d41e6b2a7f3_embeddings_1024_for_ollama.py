"""embeddings 1024 for ollama

Knowledge-base embeddings change from 768 numbers (Gemini) to 1024 (the local
qwen3-embedding:0.6b model). Vectors from different models cannot be
compared, so existing vectors are cleared and their documents are set back
to "pending"; they are re-indexed automatically at the next start.

Revision ID: 9d41e6b2a7f3
Revises: c6963be7c5da
Create Date: 2026-10-06 12:00:00
"""

from collections.abc import Sequence

from alembic import op

revision: str = "9d41e6b2a7f3"
down_revision: str | None = "c6963be7c5da"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_knowledge_chunks_embedding"


def _change_size(size: int) -> None:
    """Change the vector size, clearing old vectors and queuing re-indexing."""
    op.drop_index(INDEX, table_name="knowledge_chunks")
    op.execute(
        f"ALTER TABLE knowledge_chunks ALTER COLUMN embedding TYPE vector({size}) USING NULL"
    )
    op.execute(
        "UPDATE knowledge_documents SET status = 'pending', error = NULL, "
        "finished_at = NULL"
    )
    op.create_index(
        INDEX,
        "knowledge_chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )


def upgrade() -> None:
    """Switch to 1024-number embeddings."""
    _change_size(1024)


def downgrade() -> None:
    """Switch back to 768-number embeddings."""
    _change_size(768)
