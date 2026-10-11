"""Turns text into embeddings (lists of numbers) for semantic search.

Texts with similar meaning get similar numbers, so the knowledge base can find
passages that match a question even when the words differ (RAG).

The provider is a setting (EMBEDDING_PROVIDER / EMBEDDING_MODEL), kept in this
one module so it can be swapped:
- "ollama" (default): qwen3-embedding:0.6b running locally in Docker; the
  document text never leaves this machine.
- "google_genai": Gemini embeddings, using the same key as the LLM.
Failures become AIServiceError, like the LLM (N6).
"""

import logging
from functools import lru_cache

from langchain_core.embeddings import Embeddings
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_ollama import OllamaEmbeddings

from app.ai.errors import AIServiceError
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Numbers per embedding; must match the Vector(...) column in the database.
# 1024 is qwen3-embedding:0.6b's native size; Gemini is asked for the same.
EMBEDDING_DIMENSIONS = 1024


@lru_cache
def get_embedding_model() -> Embeddings:
    """Create the embedding model once, from the settings."""
    settings = get_settings()
    if settings.embedding_provider == "ollama":
        return OllamaEmbeddings(
            model=settings.embedding_model,
            base_url=settings.ollama_base_url,
            dimensions=EMBEDDING_DIMENSIONS,
        )
    if settings.embedding_provider == "google_genai":
        api_key = (
            settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
        )
        return GoogleGenerativeAIEmbeddings(
            model=settings.embedding_model,
            google_api_key=api_key,
            output_dimensionality=EMBEDDING_DIMENSIONS,
        )
    raise ValueError(f"Unknown EMBEDDING_PROVIDER: {settings.embedding_provider}")


def embed_documents(texts: list[str]) -> list[list[float]]:
    """Embed passages that will be stored in the knowledge base."""
    try:
        return get_embedding_model().embed_documents(texts)
    except Exception as exc:
        # Only the error type: the message could contain document text.
        logger.warning("Embedding failed: %s", type(exc).__name__)
        raise AIServiceError(
            "The AI service is unavailable. Please try again later."
        ) from exc


def embed_query(text: str) -> list[float]:
    """Embed a search question so it can be compared with stored passages."""
    try:
        return get_embedding_model().embed_query(text)
    except Exception as exc:
        logger.warning("Embedding failed: %s", type(exc).__name__)
        raise AIServiceError(
            "The AI service is unavailable. Please try again later."
        ) from exc
