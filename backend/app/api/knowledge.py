"""Knowledge base API: upload documents for RAG, list, remove and test-search.

Interviewers only (N9). Uploads are checked for size and real file type
(N8); only the extracted text is stored, never the file (N16).
"""

import logging
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependencies import CurrentUser, require_interviewer
from app.core.config import get_settings
from app.db.database import get_db
from app.db.models import KnowledgeChunk, KnowledgeDocument
from app.db.models.knowledge import KnowledgeCollection
from app.db.models.run import RunStatus
from app.knowledge import indexing
from app.knowledge.chunking import split_into_chunks
from app.knowledge.files import (
    DocumentError,
    clean_filename,
    detect_file_type,
    extract_text,
)
from app.knowledge.search import search_knowledge
from app.runs.runner import start_run

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/knowledge",
    tags=["knowledge base"],
    dependencies=[Depends(require_interviewer)],
)

NOT_FOUND = "This document no longer exists."


class DocumentOut(BaseModel):
    """A knowledge-base document as shown in the documents table."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    filename: str
    collection: KnowledgeCollection
    file_type: str
    size_bytes: int
    chunk_count: int
    status: RunStatus  # pending/running = indexing, completed = ready
    error: str | None = None
    created_at: datetime


class SearchRequest(BaseModel):
    """A test search: the question and optionally one collection."""

    query: str = Field(min_length=2, max_length=500)
    collection: KnowledgeCollection | None = None
    limit: int = Field(default=5, ge=1, le=10)


class PassageOut(BaseModel):
    """One search result shown in the retrieval test."""

    document_id: int
    filename: str
    collection: KnowledgeCollection
    text: str
    score: float


@router.get("/documents", response_model=list[DocumentOut])
def list_documents(
    db: Annotated[Session, Depends(get_db)],
    collection: KnowledgeCollection | None = None,
) -> list[KnowledgeDocument]:
    """List documents, newest first, optionally only one collection."""
    statement = select(KnowledgeDocument).order_by(KnowledgeDocument.created_at.desc())
    if collection:
        statement = statement.where(KnowledgeDocument.collection == collection)
    return list(db.scalars(statement))


@router.post(
    "/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED
)
def upload_document(
    db: Annotated[Session, Depends(get_db)],
    user: Annotated[CurrentUser, Depends(require_interviewer)],
    file: Annotated[UploadFile, File()],
    collection: Annotated[KnowledgeCollection, Form()],
) -> KnowledgeDocument:
    """Check a document, store its text as passages and start indexing."""
    max_bytes = get_settings().max_upload_mb * 1024 * 1024
    data = file.file.read(max_bytes + 1)  # read one byte more to detect "too big"
    if len(data) > max_bytes:
        raise HTTPException(
            status.HTTP_413_CONTENT_TOO_LARGE,
            f"This file is larger than {get_settings().max_upload_mb} MB.",
        )
    filename = clean_filename(file.filename or "")
    try:
        file_type = detect_file_type(data, filename)
        text = extract_text(data, file_type)
    except DocumentError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, str(exc)) from None

    chunks = split_into_chunks(text)
    document = KnowledgeDocument(
        collection=collection,
        filename=filename,
        file_type=file_type,
        size_bytes=len(data),
        chunk_count=len(chunks),
        uploaded_by_id=user.id,
    )
    db.add(document)
    db.flush()
    db.add_all(
        KnowledgeChunk(document_id=document.id, position=index, text=chunk)
        for index, chunk in enumerate(chunks)
    )
    db.commit()
    db.refresh(document)
    logger.info("Knowledge document added: %d (%d passages)", document.id, len(chunks))

    start_run(indexing.RUN_KIND, document.id)  # embeddings are made in the background
    return document


@router.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_document(
    document_id: int, db: Annotated[Session, Depends(get_db)]
) -> Response:
    """Remove a document and all its passages from the knowledge base."""
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    db.delete(document)  # passages are deleted with it (ON DELETE CASCADE)
    db.commit()
    logger.info("Knowledge document removed: %d", document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/documents/{document_id}/retry", response_model=DocumentOut)
def retry_indexing(
    document_id: int, db: Annotated[Session, Depends(get_db)]
) -> KnowledgeDocument:
    """Start indexing again for a document whose indexing failed."""
    document = db.get(KnowledgeDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    if document.status == RunStatus.FAILED:
        document.status = RunStatus.PENDING
        document.error = None
        db.commit()
        start_run(indexing.RUN_KIND, document.id)
    db.refresh(document)
    return document


@router.post("/search", response_model=list[PassageOut])
def search(
    body: SearchRequest, db: Annotated[Session, Depends(get_db)]
) -> list[PassageOut]:
    """Find the passages closest in meaning to the question (retrieval test)."""
    collections = [body.collection] if body.collection else None
    passages = search_knowledge(db, body.query, collections, body.limit)
    return [PassageOut(**vars(passage)) for passage in passages]
