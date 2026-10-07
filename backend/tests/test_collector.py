"""CV Collector: form answers → CV files + candidates (needs the database).

A fake Google source stands in for Drive and Sheets, and the intake folder
is a temporary folder, so no real Google account or CV is used.
"""

import base64
import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from app.assistant.posting import application_link
from app.auth.security import Role, create_access_token
from app.collector import collect, intake
from app.collector.collect import CollectorSetupError, collect_round, find_columns
from app.collector.google_source import GoogleSourceError, load_key
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Candidate, Job
from app.db.models.candidate import CandidateStatus
from app.main import app

pytestmark = pytest.mark.usefixtures("database_available")

HEADER = [
    "Timestamp",
    "Full name",
    "Email address",
    "Position applied for",
    "CV",
    "Consent",
]
PDF = b"%PDF-1.4 synthetic test CV"
CONSENT = "I agree that my CV and details are used to assess this application."


def docx_bytes() -> bytes:
    """A tiny Word file (a zip with word/document.xml)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", "<w:document/>")
    return buffer.getvalue()


class FakeGoogle:
    """Stands in for GoogleSource: rows of the Sheet and files in Drive."""

    def __init__(self, rows, files):
        """rows: Sheet answers (without the header); files: id -> (name, bytes)."""
        self.rows = [HEADER, *rows]
        self.files = files
        self.downloads = []
        self.broken = set()  # file ids that fail like a network error

    def response_rows(self):
        """Return the Sheet with its header row."""
        return self.rows

    def file_info(self, file_id):
        """Return a file's name and size (as Drive reports them)."""
        name, data = self.files[file_id]
        return {"name": name, "size": str(len(data))}

    def download(self, file_id):
        """Return a file's content, or fail for a broken one."""
        if file_id in self.broken:
            raise GoogleSourceError("Google could not be reached.")
        self.downloads.append(file_id)
        return self.files[file_id][1]


def answer(job_id, file_id, name="Candidate A", consent=CONSENT, position=None):
    """One form answer as a Sheet row."""
    return [
        "07/10/2026 10:00:00",
        name,
        "candidate.a@example.com",
        position or f"JOB-{job_id} · Python Developer",
        f"https://drive.google.com/open?id={file_id}",
        consent,
    ]


@pytest.fixture
def intake_dir(tmp_path, monkeypatch):
    """Use a temporary intake folder instead of the Docker volume."""
    monkeypatch.setattr(get_settings(), "cv_intake_dir", str(tmp_path))
    return tmp_path


@pytest.fixture
def job_id():
    """A test job; deleting it afterwards also deletes its candidates."""
    with SessionLocal() as db:
        job = Job(title="Python Developer")
        db.add(job)
        db.commit()
        new_id = job.id
    yield new_id
    with SessionLocal() as db:
        db.delete(db.get(Job, new_id))
        db.commit()


def candidates(job_id) -> list[Candidate]:
    """The job's candidates, oldest first."""
    with SessionLocal() as db:
        return list(db.query(Candidate).filter_by(job_id=job_id).order_by(Candidate.id))


def test_a_new_cv_is_collected_once(intake_dir, job_id):
    google = FakeGoogle(
        [answer(job_id, "file-0000001")], {"file-0000001": ("cv.pdf", PDF)}
    )

    result = collect_round(google)

    assert result.collected == 1
    (candidate,) = candidates(job_id)
    assert candidate.status == CandidateStatus.RECEIVED
    assert candidate.full_name == "Candidate A"
    assert candidate.cv_filename == "cv.pdf"
    saved = intake_dir / f"job-{job_id}" / f"{candidate.id}.pdf"
    assert saved.read_bytes() == PDF

    again = collect_round(google)  # the next round finds nothing new

    assert again.collected == 0 and len(candidates(job_id)) == 1
    assert google.downloads == ["file-0000001"]  # not downloaded twice


def test_a_word_cv_is_saved_as_docx(intake_dir, job_id):
    google = FakeGoogle(
        [answer(job_id, "file-0000002")], {"file-0000002": ("cv", docx_bytes())}
    )

    collect_round(google)

    (candidate,) = candidates(job_id)
    assert (intake_dir / f"job-{job_id}" / f"{candidate.id}.docx").exists()


def test_a_wrong_file_type_is_rejected_and_not_saved(intake_dir, job_id):
    google = FakeGoogle(
        [answer(job_id, "file-0000003")], {"file-0000003": ("photo.png", b"\x89PNG...")}
    )

    result = collect_round(google)

    assert result.rejected == 1
    (candidate,) = candidates(job_id)
    assert candidate.status == CandidateStatus.REJECTED
    assert "PDF or Word" in candidate.parse_error
    assert not (intake_dir / f"job-{job_id}").exists()


def test_a_too_large_cv_is_rejected_without_downloading(
    intake_dir, job_id, monkeypatch
):
    monkeypatch.setattr(get_settings(), "max_cv_mb", 1)
    big = b"%PDF-" + b"x" * (1024 * 1024 + 1)
    google = FakeGoogle(
        [answer(job_id, "file-0000004")], {"file-0000004": ("cv.pdf", big)}
    )

    collect_round(google)

    (candidate,) = candidates(job_id)
    assert candidate.status == CandidateStatus.REJECTED
    assert "larger than 1 MB" in candidate.parse_error
    assert google.downloads == []


def test_answers_without_job_consent_or_cv_are_skipped(intake_dir, job_id):
    rows = [
        answer(job_id, "file-0000005", position="Python Developer"),  # no JOB-id
        answer(999999999, "file-0000006"),  # job does not exist
        answer(job_id, "file-0000007", consent=""),  # no consent
        [*answer(job_id, "x")[:4], "", CONSENT],  # no CV link
    ]
    google = FakeGoogle(rows, {})

    result = collect_round(google)

    assert result.skipped == 4 and candidates(job_id) == []


def test_one_failing_cv_does_not_stop_the_others(intake_dir, job_id):
    files = {"file-0000008": ("a.pdf", PDF), "file-0000009": ("b.pdf", PDF)}
    google = FakeGoogle(
        [answer(job_id, "file-0000008"), answer(job_id, "file-0000009", "Candidate B")],
        files,
    )
    google.broken = {"file-0000008"}

    result = collect_round(google)

    assert result.failed == 1 and result.collected == 1
    assert [c.full_name for c in candidates(job_id)] == ["Candidate B"]

    google.broken = set()  # Google works again: the next round gets it
    assert collect_round(google).collected == 1


def test_a_sheet_without_a_cv_question_is_reported():
    with pytest.raises(CollectorSetupError, match="'cv'"):
        find_columns(["Timestamp", "Full name", "Email", "Position", "Consent"])


def test_the_key_can_be_json_or_base64():
    key = {"type": "service_account", "client_email": "x@example.com"}
    text = json.dumps(key)

    assert load_key(text) == key
    assert load_key(base64.b64encode(text.encode()).decode()) == key
    with pytest.raises(GoogleSourceError):
        load_key("not a key")


def test_remove_cv_deletes_the_file(intake_dir):
    path = intake.save_cv(1, 2, "pdf", PDF)

    intake.remove_cv(1, 2)

    assert not path.exists() and intake.find_cv(1, 2) is None


def test_the_job_post_link_prefills_the_job(monkeypatch):
    form = "https://docs.google.com/forms/d/e/FORMID/viewform"
    monkeypatch.setattr(get_settings(), "google_form_position_field", "entry.123")

    link = application_link(form, 12, "Python Developer")

    assert link.startswith(form + "?usp=pp_url&entry.123=JOB-12")
    assert collect.JOB_REFERENCE.search(link.replace("+", " "))
    # Short links cannot be pre-filled; without the setting nothing changes.
    assert application_link("https://forms.gle/abc", 12, "x") == "https://forms.gle/abc"
    monkeypatch.setattr(get_settings(), "google_form_position_field", None)
    assert application_link(form, 12, "x") == form


def test_interviewers_see_the_received_cvs(intake_dir, job_id):
    google = FakeGoogle(
        [answer(job_id, "file-0000010"), answer(job_id, "file-0000011", "Candidate B")],
        {"file-0000010": ("cv.pdf", PDF), "file-0000011": ("cv.txt", b"plain text")},
    )
    collect_round(google)
    client = TestClient(app)
    interviewer = {
        "Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"
    }
    candidate = {"Authorization": f"Bearer {create_access_token(1, Role.CANDIDATE)}"}

    cvs = client.get(f"/api/jobs/{job_id}/cvs", headers=interviewer).json()
    job = client.get(f"/api/jobs/{job_id}", headers=interviewer).json()

    assert sorted(c["status"] for c in cvs) == ["received", "rejected"]
    assert job["cvs_received"] == 1  # the rejected file is not counted
    assert client.get(f"/api/jobs/{job_id}/cvs", headers=candidate).status_code == 403


def test_interviewers_can_view_and_remove_an_applicant(intake_dir, job_id):
    google = FakeGoogle(
        [answer(job_id, "file-0000012")], {"file-0000012": ("cv.pdf", PDF)}
    )
    collect_round(google)
    (candidate,) = candidates(job_id)
    client = TestClient(app)
    interviewer = {
        "Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"
    }
    url = f"/api/jobs/{job_id}/cvs/{candidate.id}"

    response = client.get(f"{url}/file", headers=interviewer)

    assert response.status_code == 200 and response.content == PDF
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith("inline")
    # The applicant must belong to the job in the address.
    other = f"/api/jobs/{job_id + 1}/cvs/{candidate.id}/file"
    assert client.get(other, headers=interviewer).status_code == 404

    assert client.delete(url, headers=interviewer).status_code == 204
    assert candidates(job_id) == []
    assert intake.find_cv(job_id, candidate.id) is None  # the file is gone too


def test_candidates_cannot_view_or_remove_cvs(intake_dir, job_id):
    client = TestClient(app)
    candidate = {"Authorization": f"Bearer {create_access_token(1, Role.CANDIDATE)}"}
    url = f"/api/jobs/{job_id}/cvs/1"

    assert client.get(f"{url}/file", headers=candidate).status_code == 403
    assert client.delete(url, headers=candidate).status_code == 403
