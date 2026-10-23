"""The selection email after an approved report (§4B-14), needs the
database: preview from the knowledge-base template (or the standard text),
edit and send once, the candidate marked as selected. Synthetic data only."""

from datetime import timedelta

import pytest

from app.api.screening import _pipeline
from app.auth.security import Role, create_access_token
from app.core import clock
from app.db.database import SessionLocal
from app.db.models import AssessmentReport, Candidate, InterviewSession, Job
from app.db.models.assessment import ReviewStatus
from app.db.models.interview import InvitationStatus, SessionStatus
from app.db.models.run import RunStatus
from app.integrations.email import EmailError
from app.interviews import emails
from app.knowledge.search import Passage

pytestmark = pytest.mark.usefixtures("database_available")

INTERVIEWER = {"Authorization": f"Bearer {create_access_token(1, Role.INTERVIEWER)}"}
SELECTION = """# Email Template: Job Selection

Subject: Good news about {job_title}

Hello {candidate_name},

You have been selected for the {job_title} role.

Kind regards,
The team
"""
INVITATION = "Subject: Interview: {job_title}\n\nJoin here: {interview_link}\n"


@pytest.fixture
def mailbox(monkeypatch):
    """Fake email and knowledge base: sent emails are recorded (.fail makes
    sending fail); .documents are the templates the search finds."""
    box = type("Mailbox", (), {"sent": [], "fail": None, "documents": []})()

    def send(to, subject, text, html=None, invite=None):
        """Record the email, or fail like the email server would."""
        if box.fail:
            raise EmailError(box.fail)
        box.sent.append({"to": to, "subject": subject, "text": text, "html": html})

    def search(db, query, collections, limit):
        """Every template matches (the search ranks; the type is checked)."""
        return [
            Passage(n, f"template-{n}.md", collections[0], text, 0.9)
            for n, text in enumerate(box.documents)
        ]

    monkeypatch.setattr(emails, "send_email", send)
    monkeypatch.setattr(emails, "search_knowledge", search)
    monkeypatch.setattr(emails, "_whole_document", lambda db, n: box.documents[n])
    return box


@pytest.fixture
def approved():
    """An ended interview whose report was approved."""
    with SessionLocal() as db:
        job = Job(title="Data Analyst")
        db.add(job)
        db.flush()
        candidate = Candidate(
            job_id=job.id,
            full_name="Robin Sample",
            email="robin@example.com",
            cv_filename="cv.pdf",
        )
        db.add(candidate)
        db.flush()
        session = InterviewSession(
            candidate_id=candidate.id,
            job_id=job.id,
            scheduled_at=clock.now() - timedelta(hours=2),
            join_token_hash=f"hash-{candidate.id}",
            invitation_status=InvitationStatus.SENT,
            status=SessionStatus.ENDED,
        )
        db.add(session)
        db.flush()
        report = AssessmentReport(
            candidate_id=candidate.id,
            session_id=session.id,
            status=RunStatus.COMPLETED,
            review_status=ReviewStatus.APPROVED,
            approved_at=clock.now(),
            content={"version": 1},
        )
        db.add(report)
        db.commit()
        ids = {
            "job": job.id,
            "candidate": candidate.id,
            "session": session.id,
            "report": report.id,
        }
    yield ids
    with SessionLocal() as db:
        db.delete(db.get(Job, ids["job"]))
        db.commit()


def url(ids) -> str:
    """The interview's selection-email address."""
    return f"/api/interviews/{ids['session']}/selection-email"


def test_the_preview_uses_the_selection_template(approved, mailbox, client):
    mailbox.documents = [INVITATION, SELECTION]  # the invitation is skipped

    answer = client.get(url(approved), headers=INTERVIEWER)

    assert answer.status_code == 200
    email = answer.json()
    assert email["to"] == "robin@example.com"
    assert email["subject"] == "Good news about Data Analyst"
    assert "Hello Robin Sample," in email["text"]
    assert "selected for the Data Analyst role" in email["text"]
    assert email["template"] == "template-1.md"
    assert mailbox.sent == []  # a preview sends nothing


def test_without_a_template_the_standard_text_is_used(approved, mailbox, client):
    mailbox.documents = [INVITATION]

    email = client.get(url(approved), headers=INTERVIEWER).json()

    assert email["subject"] == (
        "Congratulations: you have been selected for the Data Analyst role"
    )
    assert "Dear Robin Sample," in email["text"]
    assert email["template"] == emails.STANDARD_NAME


def test_invitations_never_use_the_selection_template(approved, mailbox):
    mailbox.documents = [SELECTION]

    with SessionLocal() as db:
        text, name = emails.template(db)

    assert text == emails.STANDARD and name == emails.STANDARD_NAME


def test_the_checked_email_is_sent_once(approved, mailbox, client):
    edited = {"subject": "Welcome aboard", "text": "Hello Robin,\n\nYou got the job."}

    answer = client.post(url(approved), json=edited, headers=INTERVIEWER)

    assert answer.status_code == 200
    assert answer.json()["selected_at"] is not None  # the report page shows it
    (email,) = mailbox.sent
    assert email["to"] == "robin@example.com"
    assert email["subject"] == "Welcome aboard"
    assert email["text"] == "Hello Robin,\n\nYou got the job."
    assert "You got the job." in email["html"] and "href" not in email["html"]
    with SessionLocal() as db:
        candidate = db.get(Candidate, approved["candidate"])
        assert candidate.selected_at is not None
        assert _pipeline(candidate, None) == "selected"  # badge in the ranking
    again = client.post(url(approved), json=edited, headers=INTERVIEWER)
    assert again.status_code == 409 and "already sent" in again.json()["detail"]
    assert client.get(url(approved), headers=INTERVIEWER).status_code == 409
    assert len(mailbox.sent) == 1


def test_a_failed_email_does_not_mark_the_candidate(approved, mailbox, client):
    mailbox.fail = "The email server could not be reached."

    answer = client.post(
        url(approved),
        json={"subject": "Welcome aboard", "text": "You got the job."},
        headers=INTERVIEWER,
    )

    assert (
        answer.status_code == 503 and "could not be reached" in answer.json()["detail"]
    )
    with SessionLocal() as db:
        assert db.get(Candidate, approved["candidate"]).selected_at is None


@pytest.mark.parametrize(
    "review_status", [ReviewStatus.PENDING_REVIEW, ReviewStatus.CHANGES_REQUESTED]
)
def test_only_after_the_report_is_approved(approved, mailbox, client, review_status):
    with SessionLocal() as db:
        db.get(AssessmentReport, approved["report"]).review_status = review_status
        db.commit()
    email = {"subject": "Welcome aboard", "text": "You got the job."}

    for answer in (
        client.get(url(approved), headers=INTERVIEWER),
        client.post(url(approved), json=email, headers=INTERVIEWER),
    ):
        assert answer.status_code == 409 and "approved" in answer.json()["detail"]
    assert mailbox.sent == []


def test_a_candidate_without_an_email_address(approved, mailbox, client):
    with SessionLocal() as db:
        db.get(Candidate, approved["candidate"]).email = None
        db.commit()

    answer = client.get(url(approved), headers=INTERVIEWER)

    assert answer.status_code == 409 and "no email address" in answer.json()["detail"]


def test_the_email_must_have_a_subject_and_text(approved, mailbox, client):
    answer = client.post(
        url(approved), json={"subject": "", "text": "Hi"}, headers=INTERVIEWER
    )

    assert answer.status_code == 422 and mailbox.sent == []


def test_candidates_cannot_see_or_send_it(approved, mailbox, client):
    token = create_access_token(approved["session"], Role.CANDIDATE)
    candidate = {"Authorization": f"Bearer {token}"}
    email = {"subject": "Welcome aboard", "text": "You got the job."}

    assert client.get(url(approved), headers=candidate).status_code == 403
    assert client.post(url(approved), json=email, headers=candidate).status_code == 403
    assert mailbox.sent == []


def test_the_preview_shows_the_email_as_the_candidate_sees_it(approved, client):
    edited = {
        "subject": "Welcome aboard",
        "text": "Hello Robin,\n\nYou <b>got</b> the job.",
    }

    answer = client.post(f"{url(approved)}/preview", json=edited, headers=INTERVIEWER)

    assert answer.status_code == 200
    html = answer.json()["html"]
    assert "Welcome aboard" in html and "Hello Robin," in html
    assert "&lt;b&gt;got&lt;/b&gt;" in html  # the text is escaped, never markup


def test_the_reports_list_ranks_only_approved_reports(approved, client):
    with SessionLocal() as db:
        report = db.get(AssessmentReport, approved["report"])
        report.content = {
            "version": 1,
            "position": {"score": 78},
            "components": {"interview": {"overall": 74}},
        }
        db.commit()

    rows = client.get(
        f"/api/jobs/{approved['job']}/reports", headers=INTERVIEWER
    ).json()

    (row,) = rows
    assert row["rank"] == 1 and row["not_ranked"] is None
    assert row["selected_at"] is None and row["has_email"] is True
    assert row["identity"]["state"] in {"no_photo", "off"}

    with SessionLocal() as db:
        db.get(
            AssessmentReport, approved["report"]
        ).review_status = ReviewStatus.PENDING_REVIEW
        db.commit()
    (row,) = client.get(
        f"/api/jobs/{approved['job']}/reports", headers=INTERVIEWER
    ).json()
    assert row["rank"] is None and "waiting for your review" in row["not_ranked"]
