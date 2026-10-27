"""The embedding provider is chosen by settings (no network calls here)."""

import pytest
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_ollama import OllamaEmbeddings
from pydantic import SecretStr

from app.ai import embeddings
from app.ai.embeddings import EMBEDDING_DIMENSIONS, get_embedding_model
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def fresh_model():
    """Create the model again for each test (it is normally cached)."""
    get_embedding_model.cache_clear()
    yield
    get_embedding_model.cache_clear()


def test_default_is_the_local_ollama_model():
    model = get_embedding_model()

    assert isinstance(model, OllamaEmbeddings)
    assert model.model == "qwen3-embedding:0.6b"
    assert model.dimensions == EMBEDDING_DIMENSIONS == 1024


def test_gemini_can_be_chosen_instead(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_provider", "google_genai")
    monkeypatch.setattr(get_settings(), "embedding_model", "gemini-embedding-001")
    monkeypatch.setattr(get_settings(), "llm_api_key", SecretStr("test-key-not-real"))

    model = get_embedding_model()

    assert isinstance(model, GoogleGenerativeAIEmbeddings)
    assert model.output_dimensionality == EMBEDDING_DIMENSIONS


def test_unknown_provider_is_a_clear_error(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_provider", "something-else")

    with pytest.raises(ValueError, match="EMBEDDING_PROVIDER"):
        get_embedding_model()


def test_unreachable_model_is_tried_again_then_a_clear_ai_error(monkeypatch):
    calls = []

    class Down:
        """Embedding model that cannot be reached."""

        def embed_query(self, text):
            """Fail like a stopped Ollama would."""
            calls.append(text)
            raise ConnectionError("connection refused")

    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: Down())
    monkeypatch.setattr(embeddings.time, "sleep", lambda seconds: None)

    with pytest.raises(embeddings.AIServiceError):
        embeddings.embed_query("anything")
    assert len(calls) == embeddings.ATTEMPTS  # bounded: 3 tries, then the error


def test_a_busy_model_succeeds_on_a_later_try(monkeypatch):
    answers = [TimeoutError("busy"), [0.1, 0.2]]

    class Busy:
        """Embedding model that is busy once."""

        def embed_query(self, text):
            """Fail the first time, answer the second."""
            answer = answers.pop(0)
            if isinstance(answer, Exception):
                raise answer
            return answer

    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: Busy())
    monkeypatch.setattr(embeddings.time, "sleep", lambda seconds: None)

    assert embeddings.embed_query("anything") == [0.1, 0.2]
