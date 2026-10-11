"""Knowledge base for RAG (§4B-1, §4B-8): documents the Hiring Assistant can
search, split into passages ("chunks") with an embedding each.

Only the extracted text is kept, never the uploaded file (N16). Candidate
data must never be uploaded here (shown as a warning on the screen).
"""

from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.db.base import Base, TimestampMixin, status_column
from app.db.models.run import RunStateMixin


class KnowledgeCollection(StrEnum):
    """The groups of documents, as in the design (each has its own use)."""

    REFERENCE_LIBRARY = "reference_library"  # trusted references for JDs
    COMPANY_POLICIES = "company_policies"  # JDs and company-related answers
    PREVIOUS_JOB_PROFILES = "previous_job_profiles"  # examples for new JDs
    EMAIL_TEMPLATES = "email_templates"  # interview invitation emails
    QUESTION_BANK = "question_bank"  # interview questions to suggest


class KnowledgeDocument(RunStateMixin, TimestampMixin, Base):
    """One uploaded document. Status columns (RunStateMixin) track indexing:
    pending → running → completed (ready) or failed."""

    __tablename__ = "knowledge_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    collection: Mapped[KnowledgeCollection] = mapped_column(
        status_column(KnowledgeCollection), index=True
    )
    filename: Mapped[str] = mapped_column(String(255))  # cleaned, display only
    file_type: Mapped[str] = mapped_column(String(10))  # pdf, docx, txt, md
    size_bytes: Mapped[int]
    chunk_count: Mapped[int] = mapped_column(default=0)
    uploaded_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )


class KnowledgeChunk(Base):
    """One passage of a document and its embedding (empty until indexed)."""

    __tablename__ = "knowledge_chunks"
    __table_args__ = (
        # Fast "most similar" search by cosine distance (pgvector HNSW index).
        Index(
            "ix_knowledge_chunks_embedding",
            "embedding",
            postgresql_using="hnsw",
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("knowledge_documents.id", ondelete="CASCADE"), index=True
    )
    position: Mapped[int]  # order of the passage in the document
    text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS))
