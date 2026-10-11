"""Semantic search over the knowledge base (the "R" in RAG).

The question is turned into an embedding and compared with every indexed
passage by cosine distance; the closest passages are returned with a match
score between 0 and 1 (1 = same meaning).
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.embeddings import embed_query
from app.db.models import KnowledgeChunk, KnowledgeDocument
from app.db.models.knowledge import KnowledgeCollection
from app.db.models.run import RunStatus


@dataclass
class Passage:
    """One search result: the passage text and where it comes from."""

    document_id: int
    filename: str
    collection: KnowledgeCollection
    text: str
    score: float


def search_knowledge(
    db: Session,
    query: str,
    collections: list[KnowledgeCollection] | None = None,
    limit: int = 5,
) -> list[Passage]:
    """Return the passages closest in meaning to the query (best first)."""
    query_vector = embed_query(query)
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
    statement = (
        select(KnowledgeChunk, KnowledgeDocument, distance.label("distance"))
        .join(KnowledgeDocument, KnowledgeChunk.document_id == KnowledgeDocument.id)
        .where(
            KnowledgeChunk.embedding.is_not(None),
            KnowledgeDocument.status == RunStatus.COMPLETED,  # only ready documents
        )
        .order_by(distance)
        .limit(limit)
    )
    if collections:
        statement = statement.where(KnowledgeDocument.collection.in_(collections))

    return [
        Passage(
            document_id=document.id,
            filename=document.filename,
            collection=document.collection,
            text=chunk.text,
            score=round(max(0.0, 1 - float(dist)), 3),
        )
        for chunk, document, dist in db.execute(statement).all()
    ]
