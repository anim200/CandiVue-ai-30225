"""A whole "Screen CVs" run through LangGraph 2 and the API (needs the
database). Word CVs are written in a temporary intake folder; a fake
embedding (word counts) stands in for the local model.
"""

import io

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.ai import embeddings
from app.auth.security import Role, create_access_token
from app.collector import intake
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Candidate, Job, ScreeningRun
from app.graphs import cv_screening
from app.graphs.checkpointer import open_checkpointer
from app.main import app
from app.screening import matching

pytestmark = pytest.mark.usefixtures("database_available")

PROFILE = {
    "title": "PHP Developer",
    "min_years_experience": 3,
    "requirements": [
        {"text": "PHP", "level": "mandatory", "category": "skill"},
        {
            "text": "Docker",
            "level": "mandatory",
            "category": "skill",
            "also_counts": ["Laravel Sail"],
        },
        {"text": "Redis", "level": "preferred", "category": "skill"},
    ],
}
GOOD = """Alex Strong
alex.strong@example.com
Work Experience
Senior PHP Developer · Jan 2018 – Present
Builds PHP APIs with Redis; every service runs in Docker.
Education
BSc in Computer Science (2013 – 2017)
"""
SAIL = """Morgan Sail
morgan.sail@example.com
Work Experience
PHP Developer · Jan 2020 – Present
Uses Laravel Sail for local environments and PHP for everything else.
"""
NO_DOCKER = """Lee Plain
lee.plain@example.com
Work Experience
PHP Developer · Jan 2016 – Present
Deploys PHP sites to shared hosting by FTP and builds admin pages.
"""


def fake_vector(text: str) -> list[float]:
    """Bag-of-words vector (1024 numbers, like the real model): texts
    sharing words are similar."""
    vector = [0.0] * 1024
    for word in text.lower().split():
        vector[hash(word) % 1024] += 1.0
    return vector


def docx(text: str) -> bytes:
    """A Word file with one paragraph per line."""
    document = Document()
    for line in text.splitlines():
        document.add_paragraph(line)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    """No Ollama in tests: deterministic word-count vectors."""
    monkeypatch.setattr(
        matching, "embed_documents", lambda texts: [fake_vector(t) for t in texts]
    )
    monkeypatch.setattr(matching, "embed_query", fake_vector)
    monkeypatch.setattr(
        cv_screening, "embed_documents", lambda texts: [fake_vector(t) for t in texts]
    )
    monkeypatch.setattr(cv_screening, "embed_query", fake_vector)
    monkeypatch.setattr(embeddings, "embed_query", fake_vector)


@pytest.fixture
def intake_dir(tmp_path, monkeypatch):
    """A temporary intake folder instead of the Docker volume."""
    monkeypatch.setattr(get_settings(), "cv_intake_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def job_id(intake_dir):
    """A job with a profile and four CVs: two pass, one fails the gate, one
    cannot be read. Deleted afterwards (with its candidates and runs)."""
    with SessionLocal() as db:
        job = Job(title="PHP Developer", profile=PROFILE)
        db.add(job)
        db.flush()
        for name, content in [
            ("good.docx", GOOD),
            ("sail.docx", SAIL),
            ("lee.docx", NO_DOCKER),
        ]:
            candidate = Candidate(job_id=job.id, cv_filename=name)
            db.add(candidate)
            db.flush()
            intake.save_cv(job.id, candidate.id, "docx", docx(content))
        broken = Candidate(job_id=job.id, cv_filename="broken.pdf")
        db.add(broken)
        db.flush()
        intake.save_cv(job.id, broken.id, "pdf", b"%PDF-1.4 not really a pdf")
        db.commit()
        new_id = job.id
    yield new_id
    with SessionLocal() as db, open_checkpointer() as checkpointer:
        for run_id in db.scalars(
            select(ScreeningRun.id).where(ScreeningRun.job_id == new_id)
        ):
            checkpointer.delete_thread(f"{cv_screening.RUN_KIND}-{run_id}")
        db.delete(db.get(Job, new_id))
        db.commit()


def headers(role=Role.INTERVIEWER):
    """Authorization header for a test user."""
    return {"Authorization": f"Bearer {create_access_token(1, role)}"}


def test_a_screening_run_ranks_excludes_and_skips(job_id, monkeypatch):
    client = TestClient(app)
    # Run the work at once in this test instead of in the background.
    monkeypatch.setattr(
        "app.api.screening.start_run",
        lambda kind, run_id: cv_screening.run_screening(run_id),
    )

    response = client.post(f"/api/jobs/{job_id}/screenings", headers=headers())

    assert response.status_code == 200
    result = client.get(
        f"/api/jobs/{job_id}/screenings/latest", headers=headers()
    ).json()
    assert result["run"]["status"] == "completed" or result["run"]["processed"] == 4
    ranked = [r["name"] for r in result["ranked"]]
    assert ranked == ["Alex Strong", "Morgan Sail"]  # Sail counts as Docker
    assert [r["name"] for r in result["excluded"]] == ["Lee Plain"]
    assert "Docker" in result["excluded"][0]["summary"]
    assert len(result["unreadable"]) == 1
    best = result["ranked"][0]
    assert best["rank"] == 1 and 0 <= best["overall"] <= 100
    assert set(best["dimensions"]) == {"skills", "experience", "qualifications", "ats"}
    assert best["dimensions"]["skills"]["reason"]
    assert result["run"]["weights"]["source"] == "default"
    with SessionLocal() as db:
        alex = db.scalar(
            select(Candidate).where(
                Candidate.job_id == job_id, Candidate.full_name == "Alex Strong"
            )
        )
        assert alex.email == "alex.strong@example.com"  # read from the CV


def test_weights_set_by_the_interviewer_win_and_can_be_reset(job_id):
    client = TestClient(app)
    with SessionLocal() as db:
        db.get(Job, job_id).ai_weights = {
            "skills": 50,
            "experience": 20,
            "qualifications": 10,
            "ats": 20,
            "reason": "Skills first.",
        }
        db.commit()

    suggested = client.get(f"/api/jobs/{job_id}", headers=headers()).json()["weights"]
    bad = client.put(
        f"/api/jobs/{job_id}/weights",
        headers=headers(),
        json={"skills": 60, "experience": 20, "qualifications": 10, "ats": 20},
    )
    good = client.put(
        f"/api/jobs/{job_id}/weights",
        headers=headers(),
        json={"skills": 25, "experience": 25, "qualifications": 25, "ats": 25},
    )
    reset = client.delete(f"/api/jobs/{job_id}/weights", headers=headers())

    assert suggested["source"] == "ai" and suggested["reason"] == "Skills first."
    assert bad.status_code == 422
    assert good.json()["weights"]["source"] == "interviewer"
    assert good.json()["weights"]["skills"] == 25
    assert reset.json()["weights"]["source"] == "ai"


def test_screening_needs_a_profile_and_cvs(intake_dir):
    client = TestClient(app)
    with SessionLocal() as db:
        job = Job(title="Empty job")
        db.add(job)
        db.commit()
        empty_id = job.id
    try:
        response = client.post(f"/api/jobs/{empty_id}/screenings", headers=headers())
        assert response.status_code == 422
    finally:
        with SessionLocal() as db:
            db.delete(db.get(Job, empty_id))
            db.commit()


def test_only_one_run_at_a_time(job_id):
    client = TestClient(app)
    with SessionLocal() as db:
        db.add(ScreeningRun(job_id=job_id, weights={}))  # pending, not started
        db.commit()

    response = client.post(f"/api/jobs/{job_id}/screenings", headers=headers())

    assert response.status_code == 409


def test_candidates_cannot_see_or_start_screening(job_id):
    client = TestClient(app)

    assert (
        client.get(
            f"/api/jobs/{job_id}/screenings/latest", headers=headers(Role.CANDIDATE)
        ).status_code
        == 403
    )
    assert (
        client.post(
            f"/api/jobs/{job_id}/screenings", headers=headers(Role.CANDIDATE)
        ).status_code
        == 403
    )
    assert (
        client.put(
            f"/api/jobs/{job_id}/weights",
            headers=headers(Role.CANDIDATE),
            json={"skills": 25, "experience": 25, "qualifications": 25, "ats": 25},
        ).status_code
        == 403
    )
