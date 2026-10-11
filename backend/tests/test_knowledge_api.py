"""Knowledge base API against the real database (run inside Docker).

A fake embedding model stands in for Gemini: it turns each word into a
number position, so texts that share words are "close". Indexing runs
straight away instead of in the background, so the tests are predictable.
Synthetic data only; everything created is deleted afterwards.
"""

import hashlib
import math

import pytest
from fastapi.testclient import TestClient
from langchain_core.embeddings import Embeddings
from sqlalchemy import func, select

from app.ai import embeddings
from app.ai.embeddings import EMBEDDING_DIMENSIONS
from app.api import knowledge as knowledge_api
from app.auth.security import Role, create_access_token, hash_password
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import KnowledgeChunk, KnowledgeDocument, User
from app.main import app
from app.runs import runner

pytestmark = pytest.mark.usefixtures("database_available")


class WordEmbeddings(Embeddings):
    """Fake embeddings: one position per word, so shared words mean "similar"."""

    def _embed(self, text: str) -> list[float]:
        """Count the words of the text into a fixed-size vector, then normalise."""
        vector = [0.0] * EMBEDDING_DIMENSIONS
        for word in text.lower().split():
            word = word.strip(".,:;!?")
            index = (
                int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS
            )
            vector[index] += 1.0
        length = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / length for v in vector]

    def embed_documents(self, texts):
        """Embed several passages."""
        return [self._embed(text) for text in texts]

    def embed_query(self, text):
        """Embed one search question."""
        return self._embed(text)


@pytest.fixture
def client(monkeypatch):
    """App client with fake embeddings and indexing that runs immediately."""
    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: WordEmbeddings())
    monkeypatch.setattr(knowledge_api, "start_run", runner.execute_run)
    return TestClient(app)


@pytest.fixture
def headers():
    """A real (test) interviewer and their Authorization header; removed afterwards."""
    with SessionLocal() as db:
        user = User(
            email="kb.tester@example.com",
            full_name="KB Tester",
            password_hash=hash_password("not-used-here"),
        )
        db.add(user)
        db.commit()
        user_id = user.id
    yield {"Authorization": f"Bearer {create_access_token(user_id, Role.INTERVIEWER)}"}
    with SessionLocal() as db:
        for document in db.scalars(
            select(KnowledgeDocument).where(KnowledgeDocument.uploaded_by_id == user_id)
        ):
            db.delete(document)
        db.delete(db.get(User, user_id))
        db.commit()


def upload(
    client, headers, name: str, data: bytes, collection: str = "company_policies"
):
    """Upload one file to the knowledge base through the API."""
    return client.post(
        "/api/knowledge/documents",
        headers=headers,
        files={"file": (name, data, "application/octet-stream")},
        data={"collection": collection},
    )


def test_upload_indexes_the_document(client, headers):
    response = upload(
        client, headers, "leave-policy.txt", b"Employees get 20 days of paid leave."
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "leave-policy.txt"
    assert body["collection"] == "company_policies"
    assert body["chunk_count"] == 1
    listed = client.get("/api/knowledge/documents", headers=headers).json()
    document = next(d for d in listed if d["id"] == body["id"])
    assert document["status"] == "completed"  # indexed: every passage has an embedding


def test_search_finds_the_closest_passage(client, headers):
    upload(client, headers, "leave.txt", b"Employees get 20 days of paid annual leave.")
    upload(
        client,
        headers,
        "python.txt",
        b"Backend developers write Python services with FastAPI.",
        "reference_library",
    )

    hits = client.post(
        "/api/knowledge/search",
        headers=headers,
        json={"query": "Python FastAPI developers"},
    ).json()

    assert hits[0]["filename"] == "python.txt"
    assert 0 < hits[0]["score"] <= 1


def test_search_can_be_limited_to_one_collection(client, headers):
    upload(client, headers, "leave.txt", b"Employees get 20 days of paid annual leave.")
    upload(
        client,
        headers,
        "python.txt",
        b"Python services with FastAPI.",
        "reference_library",
    )

    hits = client.post(
        "/api/knowledge/search",
        headers=headers,
        json={"query": "Python FastAPI", "collection": "company_policies"},
    ).json()

    assert {hit["collection"] for hit in hits} == {"company_policies"}


def test_wrong_file_type_is_refused(client, headers):
    response = upload(client, headers, "setup.pdf", b"MZ\x90\x00 not a pdf")

    assert response.status_code == 422
    assert response.json()["detail"] == "Only PDF, DOCX, TXT or MD files can be added."


def test_too_large_file_is_refused(client, headers, monkeypatch):
    monkeypatch.setattr(get_settings(), "max_upload_mb", 1)

    response = upload(client, headers, "big.txt", b"a" * (1024 * 1024 + 1))

    assert response.status_code == 413


def test_delete_removes_document_and_passages(client, headers):
    document_id = upload(
        client, headers, "temp.txt", b"Temporary synthetic text."
    ).json()["id"]

    response = client.delete(f"/api/knowledge/documents/{document_id}", headers=headers)

    assert response.status_code == 204
    with SessionLocal() as db:
        assert db.get(KnowledgeDocument, document_id) is None
        left = db.scalar(
            select(func.count())
            .select_from(KnowledgeChunk)
            .where(KnowledgeChunk.document_id == document_id)
        )
        assert left == 0


def test_failed_indexing_shows_a_plain_message_and_can_be_retried(
    client, headers, monkeypatch
):
    class BrokenEmbeddings(WordEmbeddings):
        """Fake embedding service that is down."""

        def embed_documents(self, texts):
            """Fail like an outage would."""
            raise TimeoutError("provider timeout")

    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: BrokenEmbeddings())
    document_id = upload(client, headers, "x.txt", b"Some synthetic text.").json()["id"]
    listed = client.get("/api/knowledge/documents", headers=headers).json()
    document = next(d for d in listed if d["id"] == document_id)
    assert document["status"] == "failed"
    assert document["error"] == runner.AI_FAILURE_MESSAGE  # plain message, no details

    monkeypatch.setattr(embeddings, "get_embedding_model", lambda: WordEmbeddings())
    retried = client.post(
        f"/api/knowledge/documents/{document_id}/retry", headers=headers
    )

    assert retried.json()["status"] == "completed"


def test_candidates_cannot_use_the_knowledge_base(client):
    candidate = {"Authorization": f"Bearer {create_access_token(1, Role.CANDIDATE)}"}

    assert client.get("/api/knowledge/documents", headers=candidate).status_code == 403
