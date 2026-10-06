"""Turns text into embeddings (lists of numbers) for semantic search.

Texts with similar meaning get similar numbers, so the knowledge base can find
passages that match a question even when the words differ (RAG). The model is
a setting (EMBEDDING_MODEL), kept in this one module so it can be swapped.
Failures become AIServiceError, like the LLM (N6).
"""

import logging
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings

from app.ai.llm import AIServiceError
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Numbers per embedding; must match the Vector(...) column in the database.
EMBEDDING_DIMENSIONS = 768


@lru_cache
def get_embedding_model() -> Embeddings:
    """Create the embedding model once, from the settings."""
    settings = get_settings()
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    return GoogleGenerativeAIEmbeddings(
        model=settings.embedding_model,
        google_api_key=api_key,
        output_dimensionality=EMBEDDING_DIMENSIONS,
    )


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed passages that will be stored in the knowledge base."""
    try:
        return get_embedding_model().embed_documents(texts)
    except Exception as exc:
        # Only the error type: the message could contain document text.
        logger.warning("Embedding failed: %s", type(exc).__name__)
        raise AIServiceError("The AI service is unavailable.") from exc


def embed_query(text: str) -> list[float]:
    """Embed a search question so it can be compared with stored passages."""
    try:
        return get_embedding_model().embed_query(text)
    except Exception as exc:
        logger.warning("Embedding failed: %s", type(exc).__name__)
        raise AIServiceError("The AI service is unavailable.") from exc
