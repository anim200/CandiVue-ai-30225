"""CV Collector: form answers → CV files + candidates (needs the database).

A fake Google source stands in for Drive and Sheets, and the intake folder
is a temporary folder, so no real Google account or CV is used.
"""

import base64
import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.assistant.posting import application_link
from app.auth.security import Role, create_access_token
from app.collector import collect, intake, photo_round
from app.collector.collect import CollectorSetupError, collect_round, find_columns
from app.collector.google_source import GoogleSourceError, load_key
from app.collector.photo_round import process_photos
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import Candidate, InterviewSession, Job
from app.db.models.candidate import CandidateStatus
from app.db.models.interview import InvitationStatus
from app.identity import references
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
SENT = 46302.5  # 7 Oct 2026, 12:00 in the Sheet's time zone (days since 30 Dec 1899)
SENT_UTC = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)  # the same moment (Dhaka is +6)
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

    def time_zone(self):
        """The Sheet's time zone (the submission times are local to it)."""
        return "Asia/Dhaka"

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
        SENT,  # Sheets sends the submission time as a number
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


def test_interviewers_can_upload_cvs_by_hand(intake_dir, job_id):
    client = TestClient(app)
    interviewer = {
        "Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"
    }
    files = [
        ("files", ("07-taylor_draft-CV.pdf", PDF, "application/pdf")),
        ("files", ("cv.docx", docx_bytes(), "application/octet-stream")),
        ("files", ("notes.txt", b"not a cv", "text/plain")),
    ]

    response = client.post(f"/api/jobs/{job_id}/cvs", headers=interviewer, files=files)

    assert response.status_code == 200
    results = response.json()
    assert [r["added"] for r in results] == [True, True, False]
    assert "PDF or Word" in results[2]["message"]  # one bad file, the rest added
    first, second = candidates(job_id)
    assert first.full_name == "Taylor Draft"  # guessed from the file name
    assert second.full_name is None  # "cv.docx" has no name in it
    assert intake.find_cv(job_id, first.id).suffix == ".pdf"
    assert intake.find_cv(job_id, second.id).suffix == ".docx"
    cvs = client.get(f"/api/jobs/{job_id}/cvs", headers=interviewer).json()
    assert {c["source"] for c in cvs} == {"upload"}


def test_an_upload_has_a_file_limit(intake_dir, job_id):
    client = TestClient(app)
    interviewer = {
        "Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"
    }
    files = [("files", (f"cv{i}.pdf", PDF, "application/pdf")) for i in range(31)]

    response = client.post(f"/api/jobs/{job_id}/cvs", headers=interviewer, files=files)

    assert response.status_code == 422 and candidates(job_id) == []


def test_candidates_cannot_upload_cvs(job_id):
    client = TestClient(app)
    candidate = {"Authorization": f"Bearer {create_access_token(1, Role.CANDIDATE)}"}
    files = [("files", ("cv.pdf", PDF, "application/pdf"))]

    response = client.post(f"/api/jobs/{job_id}/cvs", headers=candidate, files=files)

    assert response.status_code == 403


def set_deadline(job_id, closes_at):
    """Set the job's closing date."""
    with SessionLocal() as db:
        db.get(Job, job_id).applications_close_at = closes_at
        db.commit()


def test_a_cv_sent_after_the_closing_date_is_not_collected(intake_dir, job_id):
    set_deadline(job_id, SENT_UTC - timedelta(minutes=1))
    google = FakeGoogle(
        [answer(job_id, "file-0000020")], {"file-0000020": ("cv.pdf", PDF)}
    )

    result = collect_round(google)

    assert result.late == 1 and result.collected == 0
    assert candidates(job_id) == [] and google.downloads == []  # nothing stored


def test_a_cv_sent_in_time_is_collected_even_after_the_close(intake_dir, job_id):
    # Sent one minute before the close, collected later: the form's time counts.
    set_deadline(job_id, SENT_UTC + timedelta(minutes=1))
    google = FakeGoogle(
        [answer(job_id, "file-0000021")], {"file-0000021": ("cv.pdf", PDF)}
    )

    assert collect_round(google).collected == 1


def test_no_cvs_by_hand_after_the_closing_date(intake_dir, job_id):
    set_deadline(job_id, datetime.now(UTC) - timedelta(hours=1))
    client = TestClient(app)
    interviewer = {
        "Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"
    }
    files = [("files", ("cv.pdf", PDF, "application/pdf"))]

    response = client.post(f"/api/jobs/{job_id}/cvs", headers=interviewer, files=files)

    assert response.status_code == 409
    assert "Applications closed" in response.json()["detail"]
    assert candidates(job_id) == []


# ---------- the application photo (F7, §4B-15) ----------

PHOTO_COLUMNS = [
    "Photo of your face",
    "Photo consent: you may use my photo at the interview",
]


def with_photo(row: list, photo_id: str | None, consent: str = "Yes") -> list:
    """A form answer that also has the photo and photo-consent questions."""
    link = f"https://drive.google.com/open?id={photo_id}" if photo_id else ""
    return [*row, link, consent]


def test_the_photo_and_its_consent_are_recorded_not_downloaded(intake_dir, job_id):
    google = FakeGoogle(
        [
            with_photo(answer(job_id, "file-0000001"), "photo-000001"),
            with_photo(
                answer(job_id, "file-0000002", name="B"), "photo-000002", consent=""
            ),
            with_photo(answer(job_id, "file-0000003", name="C"), None),
        ],
        {f"file-000000{i}": ("cv.pdf", PDF) for i in (1, 2, 3)},
    )
    google.rows[0] = HEADER + PHOTO_COLUMNS

    collect_round(google)

    got = [(c.photo_file_id, c.photo_consent) for c in candidates(job_id)]
    assert got == [("photo-000001", True), ("photo-000002", False), (None, False)]
    assert all(d.startswith("file-") for d in google.downloads)  # photos wait


@pytest.fixture
def invited(job_id, monkeypatch):
    """An invited applicant with a photo; the photo model is a fake."""
    monkeypatch.setattr(
        get_settings(), "face_reference_key", SecretStr(Fernet.generate_key().decode())
    )
    monkeypatch.setattr(
        references,
        "prepare",
        lambda data: (np.eye(1, 128, dtype=np.float32)[0], b"jpeg"),
    )
    with SessionLocal() as db:
        candidate = Candidate(
            job_id=job_id,
            full_name="Candidate A",
            cv_filename="cv.pdf",
            photo_file_id="photo-000001",
            photo_consent=True,
        )
        db.add(candidate)
        db.flush()
        db.add(
            InterviewSession(
                candidate_id=candidate.id,
                job_id=job_id,
                scheduled_at=datetime.now(UTC) + timedelta(days=1),
                join_token_hash=f"hash-{candidate.id}",
                invitation_status=InvitationStatus.SENT,
            )
        )
        db.commit()
        return candidate.id


def photo_status(candidate_id: int) -> str:
    """Where the candidate's application photo stands."""
    with SessionLocal() as db:
        return references.photo_state(db, db.get(Candidate, candidate_id))


def test_an_invited_applicants_photo_is_processed_once(invited):
    google = FakeGoogle([], {"photo-000001": ("me.jpg", b"\xff\xd8\xff photo")})

    first = process_photos(google)
    again = process_photos(google)

    assert (first.ready, again.ready) == (1, 0)
    assert google.downloads == ["photo-000001"]
    assert photo_status(invited) == "ready"


def test_a_too_large_photo_is_refused_without_downloading(invited, monkeypatch):
    monkeypatch.setattr(photo_round, "MAX_PHOTO_BYTES", 10)
    google = FakeGoogle([], {"photo-000001": ("me.jpg", b"x" * 11)})

    assert process_photos(google).unusable == 1
    assert google.downloads == [] and photo_status(invited) == "too_large"


def test_a_failed_photo_download_is_tried_next_round(invited):
    google = FakeGoogle([], {"photo-000001": ("me.jpg", b"\xff\xd8\xff photo")})
    google.broken.add("photo-000001")

    assert process_photos(google).failed == 1
    assert photo_status(invited) == "download_failed"

    google.broken.clear()
    assert process_photos(google).ready == 1


def test_without_the_key_no_photo_is_processed(invited, monkeypatch):
    monkeypatch.setattr(get_settings(), "face_reference_key", None)
    google = FakeGoogle([], {"photo-000001": ("me.jpg", b"\xff\xd8\xff photo")})

    assert process_photos(google).ready == 0 and google.downloads == []


def test_photo_questions_may_come_before_the_privacy_consent():
    header = [
        "Timestamp",
        "Full name",
        "Email address",
        "Position applied for",
        "Upload your CV (PDF or Word)",
        "Photo of your face",
        "Photo consent",
        "Privacy consent",
        "Talent pool: other vacancies (optional)",
    ]

    columns = find_columns(header)

    assert columns["consent"] == 7  # the privacy consent, not the photo one
    assert (columns["photo"], columns["photo_consent"]) == (5, 6)
    assert columns["cv"] == 4 and columns["talent_pool"] == 8
