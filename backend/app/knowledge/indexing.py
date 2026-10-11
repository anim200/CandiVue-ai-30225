"""Background indexing: adds an embedding to every passage of a document.

Runs through the background runner (app/runs), so the upload answers at once
and the screen shows "Indexing" until the document is ready (N4). If the AI
service fails, the document shows a plain "failed" message (N6); passages
already embedded are kept, so "try again" only does the rest.
"""

from sqlalchemy import select

from app.ai.embeddings import embed_documents
from app.db.database import SessionLocal
from app.db.models import KnowledgeChunk, KnowledgeDocument
from app.runs.runner import register_run_kind

RUN_KIND = "knowledge_indexing"
BATCH_SIZE = 50  # passages sent to the embedding model per call


def index_document(document_id: int) -> None:
    """Embed every passage of the document that has no embedding yet."""
    while True:
        with SessionLocal() as db:
            chunks = db.scalars(
                select(KnowledgeChunk)
                .where(
                    KnowledgeChunk.document_id == document_id,
                    KnowledgeChunk.embedding.is_(None),
                )
                .order_by(KnowledgeChunk.position)
                .limit(BATCH_SIZE)
            ).all()
            if not chunks:
                return  # all passages are embedded: the runner marks it completed
            vectors = embed_documents([chunk.text for chunk in chunks])
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk.embedding = vector
            db.commit()  # saved batch by batch, so a restart keeps finished work


register_run_kind(RUN_KIND, KnowledgeDocument, index_document)
