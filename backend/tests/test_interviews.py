"""Shortlist and interview invitations (needs the database).

A screened job is made directly in the database (no CVs or AI needed):
three ranked candidates (two with the same score) and one excluded. A
scripted LLM drives the chat for the end-to-end tests.
"""

from datetime import date, datetime, time, timedelta

import pytest
from helpers import call
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.auth.security import Role, create_access_token, hash_password
from app.core import clock
from app.db.database import SessionLocal
from app.db.models import (
    Candidate,
    CandidateScore,
    InterviewSession,
    Job,
    ScreeningRun,
    User,
)
from app.db.models.candidate import CandidateStatus
from app.db.models.interview import InvitationStatus, SessionStatus
from app.db.models.knowledge import KnowledgeCollection
from app.db.models.run import RunStatus
from app.graphs import hiring_assistant
from app.graphs.checkpointer import open_checkpointer
from app.integrations.email import EmailError
from app.interviews import emails, planning, ranking, shortlist
from app.knowledge.search import Passage
from app.screening.weights import DIMENSIONS, effective_weights

pytestmark = pytest.mark.usefixtures("database_available")

PROFILE = {
    "title": "PHP Developer",
    "min_years_experience": 3,
    "requirements": [
        {"text": "PHP", "level": "mandatory", "category": "skill"},
        {"text": "Docker", "level": "required", "category": "skill"},
    ],
}
# name, overall, skills score, meets Docker, email (None = excluded by the gate)
PEOPLE = [
    ("Alex Strong", 90, 92, True, "alex@example.com"),
    ("Bea Good", 80, 85, True, "bea@example.com"),
    ("Cam Fine", 80, 70, False, None),
    ("Dee Out", None, None, False, "dee@example.com"),
]


@pytest.fixture(autouse=True)
def mailbox(monkeypatch):
    """No real email and no template search: sent emails are recorded here
    (set .fail to make sending fail; .templates to fake the knowledge base)."""
    box = type("Mailbox", (), {"sent": [], "fail": None, "templates": []})()

    def send(to, subject, text, html=None):
        """Record the email, or fail like the email server would."""
        if box.fail:
            raise EmailError(box.fail)
        box.sent.append({"to": to, "subject": subject, "text": text, "html": html})
        return {"sent_to": to, "message_id": "<1@test>"}

    monkeypatch.setattr(emails, "send_email", send)
    monkeypatch.setattr(emails, "search_knowledge", lambda *args: box.templates)
    monkeypatch.setattr(emails, "_whole_document", lambda db, document_id: TEMPLATE)
    return box


def local_iso(days_ahead: int, hour: int, minute: int = 0) -> str:
    """A local start time on a weekday, as the LLM would give it."""
    day = clock.now().astimezone(clock.local_zone()).date() + timedelta(days_ahead)
    while day.weekday() >= 5:
        day += timedelta(days=1)
    return f"{day.isoformat()}T{hour:02d}:{minute:02d}"


@pytest.fixture
def screened():
    """A job whose applications closed yesterday and whose CVs were screened
    after that; ids of its interviewer and candidates."""
    with SessionLocal() as db:
        user = User(
            email="iv.tester@example.com",
            full_name="IV Tester",
            password_hash=hash_password("x" * 10),
        )
        db.add(user)
        db.flush()
        job = Job(
            title="PHP Developer",
            profile=PROFILE,
            created_by_id=user.id,
            applications_close_at=clock.now() - timedelta(days=1),
        )
        db.add(job)
        db.flush()
        run = ScreeningRun(
            job_id=job.id, status=RunStatus.COMPLETED, weights=effective_weights(job)
        )
        db.add(run)
        db.flush()
        ids = {}
        for rank, (name, overall, skills, docker, email) in enumerate(PEOPLE, 1):
            ranked = overall is not None
            candidate = Candidate(
                job_id=job.id,
                full_name=name,
                email=email,
                cv_filename=f"{name}.pdf",
                status=CandidateStatus.PARSED,
            )
            db.add(candidate)
            db.flush()
            dims = {
                d: {"label": d, "score": skills if d == "skills" else overall}
                for d in DIMENSIONS
            }
            matches = [
                {"requirement": "PHP", "status": "met" if ranked else "unmet"},
                {"requirement": "Docker", "status": "met" if docker else "unmet"},
            ]
            db.add(
                CandidateScore(
                    screening_run_id=run.id,
                    candidate_id=candidate.id,
                    passed_gate=ranked,
                    rank=rank if ranked else None,
                    overall_score=overall,
                    dimension_scores=dims if ranked else {},
                    requirement_matches=matches,
                    summary=None if ranked else "No PHP found in the CV (mandatory).",
                )
            )
            ids[name.split()[0]] = candidate.id
        db.commit()
        data = {"job_id": job.id, "user_id": user.id, **ids}
    yield data
    with open_checkpointer() as checkpointer, SessionLocal() as db:
        checkpointer.delete_thread(f"{hiring_assistant.THREAD_KIND}-{data['job_id']}")
        db.delete(db.get(Job, data["job_id"]))  # candidates, scores, interviews
        db.delete(db.get(User, data["user_id"]))
        db.commit()


def rows(job_id):
    """The latest ranking rows of the job."""
    with SessionLocal() as db:
        return ranking.latest_rows(db, db.get(Job, job_id))[1]


def names(picked):
    """The names of chosen rows."""
    return [row.name for row in picked]


def pick(job_id, **criteria):
    """Apply shortlist criteria to the test job: (names, notes)."""
    chosen, notes = shortlist.choose(
        rows(job_id), ["PHP", "Docker"], shortlist.Criteria(**criteria)
    )
    return names(chosen), notes


def shortlist_people(job_id, *people_ids):
    """Put these candidates on the shortlist."""
    with SessionLocal() as db:
        for candidate_id in people_ids:
            db.get(Candidate, candidate_id).shortlisted_at = clock.now()
        db.commit()


def plan(data, action="invite", items=(), **options):
    """make_plan() for the test job and interviewer."""
    with SessionLocal() as db:
        return planning.make_plan(
            db, data["job_id"], data["user_id"], action, list(items), **options
        )


# ---------- choosing the shortlist ----------


def test_top_n_mentions_a_tie_at_the_cut(screened):
    chosen, notes = pick(screened["job_id"], top=2)

    assert chosen == ["Alex Strong", "Bea Good"]
    assert any("same score" in note for note in notes)  # Bea and Cam: both 80


def test_criteria_are_combined(screened):
    job_id = screened["job_id"]

    assert pick(job_id, min_overall=85)[0] == ["Alex Strong"]
    assert pick(job_id, rank_from=2, rank_to=3)[0] == ["Bea Good", "Cam Fine"]
    assert pick(job_id, minimums={"skills": 80}, must_meet=["docker"])[0] == [
        "Alex Strong",
        "Bea Good",
    ]


def test_excluded_and_unknown_names_are_explained(screened):
    chosen, notes = pick(screened["job_id"], names=["Dee", "Zed", "o"])

    assert chosen == []
    assert any("Dee Out is not ranked: No PHP found" in note for note in notes)
    assert any("No applicant called “Zed”" in note for note in notes)
    assert any("matches" in note and "say which" in note for note in notes)


def test_too_few_unknown_requirement_and_nobody(screened):
    job_id = screened["job_id"]

    chosen, notes = pick(job_id, top=10, must_meet=["Kubernetes"])
    assert len(chosen) == 3
    assert any("no requirement called “Kubernetes”" in note for note in notes)
    assert any("Only 3 match" in note for note in notes)

    chosen, notes = pick(job_id, min_overall=99)
    assert chosen == [] and "Nobody matches" in notes[-1]


def test_shortlist_replace_add_and_remove(screened):
    job_id = screened["job_id"]
    by_name = {row.name: row for row in rows(job_id)}

    def change(action, *people):
        """Save a change and return the shortlisted names."""
        with SessionLocal() as db:
            shortlist.save(
                db, db.get(Job, job_id), action, [by_name[p] for p in people]
            )
            db.commit()
        return sorted(row.name for row in rows(job_id) if row.candidate.shortlisted_at)

    assert change("replace", "Alex Strong", "Bea Good") == ["Alex Strong", "Bea Good"]
    assert change("add", "Cam Fine") == ["Alex Strong", "Bea Good", "Cam Fine"]
    assert change("remove", "Bea Good") == ["Alex Strong", "Cam Fine"]
    assert change("replace", "Bea Good") == ["Bea Good"]


# ---------- planning invitations ----------


def test_only_shortlisted_ranked_candidates_can_be_invited(screened):
    shortlist_people(screened["job_id"], screened["Alex"], screened["Dee"])
    when = local_iso(2, 10)

    result = plan(
        screened,
        items=[
            {"candidate_id": screened["Alex"], "starts_at": when},
            {"candidate_id": screened["Cam"], "starts_at": local_iso(2, 11)},
            {"candidate_id": screened["Dee"], "starts_at": local_iso(2, 12)},
        ],
    )

    alex, cam, dee = result.items
    assert alex["problem"] is None and not result.problems
    assert "Not on the shortlist" in cam["problem"]
    assert "Not ranked: No PHP found" in dee["problem"]  # excluded never invited
    assert not result.ok


def test_times_are_checked(screened):
    shortlist_people(
        screened["job_id"], screened["Alex"], screened["Bea"], screened["Cam"]
    )
    same = local_iso(3, 10)

    result = plan(
        screened,
        items=[
            {"candidate_id": screened["Alex"], "starts_at": same},
            {"candidate_id": screened["Bea"], "starts_at": local_iso(3, 10, 30)},
            {"candidate_id": screened["Cam"], "starts_at": "2020-01-01T10:00"},
        ],
    )

    alex, bea, cam = result.items
    assert alex["problem"] is None
    assert "Overlaps Alex Strong" in bea["problem"]  # 45-minute interviews
    assert "past" in cam["problem"]

    early = plan(
        screened,
        items=[{"candidate_id": screened["Cam"], "starts_at": local_iso(3, 7)}],
    )
    (item,) = early.items
    assert item["problem"] is None
    assert "Outside working hours (09:00–17:00)." in item["warnings"]
    assert "No email address." in item["warnings"]


def test_invitations_wait_for_the_close_and_a_new_screening(screened):
    shortlist_people(screened["job_id"], screened["Alex"])
    items = [{"candidate_id": screened["Alex"], "starts_at": local_iso(2, 10)}]

    def set_close(when):
        """Change the job's closing date."""
        with SessionLocal() as db:
            db.get(Job, screened["job_id"]).applications_close_at = when
            db.commit()

    set_close(clock.now() + timedelta(days=1))
    assert "Applications are open until" in plan(screened, items=items).problems[0]

    set_close(clock.now())  # closed after the screening ran
    assert "screen the CVs again" in plan(screened, items=items).problems[0]

    set_close(None)
    assert "Set when applications close" in plan(screened, items=items).problems[0]


def test_confirmed_plan_creates_interviews_and_checks_again(screened):
    shortlist_people(screened["job_id"], screened["Alex"], screened["Bea"])
    items = [
        {"candidate_id": screened["Alex"], "starts_at": local_iso(2, 10)},
        {"candidate_id": screened["Bea"], "starts_at": local_iso(2, 11)},
    ]

    with SessionLocal() as db:
        checked = planning.make_plan(
            db, screened["job_id"], screened["user_id"], "invite", items
        )
        results = planning.apply(db, checked, screened["job_id"], screened["user_id"])
        sessions = db.scalars(
            select(InterviewSession).where(
                InterviewSession.job_id == screened["job_id"]
            )
        ).all()

    assert [r["done"] for r in results] == [True, True]
    assert len(sessions) == 2 and all(len(s.join_token_hash) == 64 for s in sessions)
    assert {s.duration_minutes for s in sessions} == {45}

    again = plan(screened, items=items[:1])
    assert "Already invited" in again.items[0]["problem"]


def test_reschedule_and_cancel(screened):
    shortlist_people(screened["job_id"], screened["Alex"])
    alex = screened["Alex"]
    with SessionLocal() as db:
        first = planning.make_plan(
            db,
            screened["job_id"],
            screened["user_id"],
            "invite",
            [{"candidate_id": alex, "starts_at": local_iso(2, 10)}],
        )
        planning.apply(db, first, screened["job_id"], screened["user_id"])

        # Moving an interview may overlap its own old time.
        moved = planning.make_plan(
            db,
            screened["job_id"],
            screened["user_id"],
            "reschedule",
            [{"candidate_id": alex, "starts_at": local_iso(2, 10, 15)}],
        )
        assert moved.ok
        planning.apply(db, moved, screened["job_id"], screened["user_id"])
        cancel = planning.make_plan(
            db,
            screened["job_id"],
            screened["user_id"],
            "cancel",
            [{"candidate_id": alex}],
        )
        planning.apply(db, cancel, screened["job_id"], screened["user_id"])
        session = db.scalar(
            select(InterviewSession).where(InterviewSession.candidate_id == alex)
        )

    local = session.scheduled_at.astimezone(clock.local_zone())
    assert local.strftime("%H:%M") == "10:15"
    assert session.status == SessionStatus.CANCELLED
    nothing = plan(screened, "cancel", [{"candidate_id": alex}])
    assert "no scheduled interview" in nothing.items[0]["problem"]


def test_free_slots_skip_weekends_and_booked_times(screened):
    monday = date.fromisoformat(local_iso(7, 9)[:10])
    monday -= timedelta(days=monday.weekday())  # a Monday a week or so ahead
    with SessionLocal() as db:
        booked = datetime.combine(monday, time(9), clock.local_zone())
        db.add(
            InterviewSession(
                candidate_id=screened["Alex"],
                job_id=screened["job_id"],
                interviewer_id=screened["user_id"],
                scheduled_at=booked,
                join_token_hash="0" * 64,
            )
        )
        db.commit()
        slots = planning.free_slots(
            db,
            screened["user_id"],
            (monday - timedelta(days=2), monday),  # Saturday to Monday
            (time(9), time(12)),
            count=10,
        )

    local = [s.astimezone(clock.local_zone()).strftime("%a %H:%M") for s in slots]
    assert local == ["Mon 10:00", "Mon 11:00"]  # 09:00 is booked; 45 min + break


# ---------- the whole flow through the chat and the API ----------


def test_shortlist_then_invite_through_the_chat(screened, client, scripted, mailbox):
    headers = {
        "Authorization": f"Bearer {create_access_token(screened['user_id'], Role.INTERVIEWER)}"
    }
    job_id = screened["job_id"]
    say = lambda text: client.post(
        f"/api/assistant/jobs/{job_id}/messages", headers=headers, json={"text": text}
    )
    scripted += [
        call("update_shortlist", {"top": 2}),
        AIMessage(content="Alex and Bea are shortlisted. Bea and Cam tie at 80."),
    ]

    thread = say("Shortlist the top 2.").json()

    card = next(i for i in thread["items"] if i["kind"] == "shortlist")
    assert [c["name"] for c in card["candidates"]] == ["Alex Strong", "Bea Good"]
    assert any("same score" in note for note in card["notes"])

    alex_time = local_iso(2, 10)
    scripted += [
        call(
            "propose_invitations",
            {
                "invitations": [
                    {"candidate_id": screened["Alex"], "starts_at": alex_time},
                    {"candidate_id": screened["Bea"], "starts_at": local_iso(2, 11)},
                ]
            },
        ),
        AIMessage(content="The interviews are booked."),
    ]
    thread = say("Invite them on that day at 10 and 11.").json()

    pending = thread["pending_review"]
    assert pending["kind"] == "invitation_confirmation" and len(pending["items"]) == 2
    assert say("Hello?").status_code == 409  # the card must be answered first
    with SessionLocal() as db:
        assert (
            db.scalar(select(InterviewSession).where(InterviewSession.job_id == job_id))
            is None
        )

    # The interviewer leaves Bea out and moves Alex by half an hour.
    later = local_iso(2, 10, 30)
    thread = client.post(
        f"/api/assistant/jobs/{job_id}/invitation-decision",
        headers=headers,
        json={
            "action": "confirm",
            "items": [{"candidate_id": screened["Alex"], "starts_at": later}],
        },
    ).json()

    result = next(i for i in thread["items"] if i["kind"] == "invitations")
    assert [r["name"] for r in result["results"]] == ["Alex Strong"]
    upcoming = client.get("/api/interviews", headers=headers).json()
    (interview,) = [i for i in upcoming if i["job_id"] == job_id]
    when = datetime.fromisoformat(interview["scheduled_at"]).astimezone(
        clock.local_zone()
    )
    assert when.strftime("%Y-%m-%dT%H:%M") == later
    assert interview["invitation_status"] == "sent"

    # The emailed link works; cancelling stops it.
    link = mailbox.sent[-1]["text"].split("/join/")[1].split()[0]
    token = {"link_token": link}
    joined = client.post("/api/auth/candidate", json=token)
    assert joined.status_code == 200
    candidate = {"Authorization": f"Bearer {joined.json()['access_token']}"}
    assert client.get("/api/interviews", headers=candidate).status_code == 403
    cancel = client.post(f"/api/interviews/{interview['id']}/cancel", headers=headers)
    assert cancel.status_code == 204
    assert client.post("/api/auth/candidate", json=token).status_code == 410

    ranked = client.get(f"/api/jobs/{job_id}/screenings/latest", headers=headers).json()
    pipeline = {r["name"]: r["pipeline"] for r in ranked["ranked"]}
    assert pipeline == {
        "Alex Strong": "shortlisted",
        "Bea Good": "shortlisted",
        "Cam Fine": "new",
    }


def test_cancelling_the_card_saves_nothing(screened, client, scripted):
    headers = {
        "Authorization": f"Bearer {create_access_token(screened['user_id'], Role.INTERVIEWER)}"
    }
    job_id = screened["job_id"]
    shortlist_people(job_id, screened["Alex"])
    scripted += [
        call(
            "propose_invitations",
            {
                "invitations": [
                    {"candidate_id": screened["Alex"], "starts_at": local_iso(2, 10)}
                ]
            },
        ),
        AIMessage(content="Okay, nothing was booked."),
    ]
    client.post(
        f"/api/assistant/jobs/{job_id}/messages",
        headers=headers,
        json={"text": "Invite Alex."},
    )

    thread = client.post(
        f"/api/assistant/jobs/{job_id}/invitation-decision",
        headers=headers,
        json={"action": "cancel"},
    ).json()

    assert thread["pending_review"] is None
    with SessionLocal() as db:
        assert (
            db.scalar(select(InterviewSession).where(InterviewSession.job_id == job_id))
            is None
        )


def test_a_plan_with_problems_goes_back_to_the_llm(screened, client, scripted):
    headers = {
        "Authorization": f"Bearer {create_access_token(screened['user_id'], Role.INTERVIEWER)}"
    }
    job_id = screened["job_id"]
    scripted += [
        call(
            "propose_invitations",
            {
                "invitations": [
                    {"candidate_id": screened["Cam"], "starts_at": local_iso(2, 10)}
                ]
            },
        ),
        AIMessage(content="Cam is not on the shortlist yet. Shall I add Cam?"),
    ]

    thread = client.post(
        f"/api/assistant/jobs/{job_id}/messages",
        headers=headers,
        json={"text": "Invite Cam."},
    ).json()

    assert thread["pending_review"] is None  # no card: the LLM explains instead
    assert thread["items"][-1]["text"].startswith("Cam is not on the shortlist")


# ---------- invitation emails ----------

TEMPLATE = """# Email Template: Interview Invitation

Subject: Interview invitation: {job_title}

Hello {candidate_name},

Thank you for applying for the {job_title} role. We enjoyed reading your
application and would like to invite you to a video interview.

- **Date and time:** {date}, {time} (Bangladesh time)
- **Format:** a video call with one interviewer, in your browser. You don't
  need an account.
- **Your personal link:** {interview_link}

Kind regards,
The hiring team

---

# Email Template: Reminder
Subject: Reminder
"""


def invite(screened, *people):
    """Shortlist and invite these candidates two days ahead: the results."""
    shortlist_people(screened["job_id"], *people)
    items = [
        {"candidate_id": person, "starts_at": local_iso(2, 9 + i)}
        for i, person in enumerate(people)
    ]
    with SessionLocal() as db:
        checked = planning.make_plan(
            db, screened["job_id"], screened["user_id"], "invite", items
        )
        return checked, planning.apply(
            db, checked, screened["job_id"], screened["user_id"]
        )


def test_invited_candidates_get_the_knowledge_base_template(screened, mailbox):
    mailbox.templates = [
        Passage(
            1,
            "interview-invitation.md",
            KnowledgeCollection.EMAIL_TEMPLATES,
            TEMPLATE,
            0.9,
        )
    ]

    checked, results = invite(screened, screened["Alex"])

    assert checked.email["template"] == "interview-invitation.md"  # card preview
    assert emails.PREVIEW_LINK in checked.email["text"]
    assert results[0]["email"] == "sent"
    (mail,) = mailbox.sent
    assert mail["to"] == "alex@example.com"
    assert mail["subject"] == "Interview invitation: PHP Developer"
    text = mail["text"]
    assert "Hello Alex Strong," in text and "**" not in text and "Reminder" not in text
    # Wrapped lines become whole sentences; the sign-off keeps its lines.
    assert "We enjoyed reading your application and would like" in text
    assert (
        "Format: a video call with one interviewer, in your browser. You don't need"
        in text
    )
    assert "Kind regards,\nThe hiring team" in text
    assert "(Asia/Dhaka)" not in text and "(Bangladesh time)" in text  # one zone only
    html = mail["html"]
    assert ">Join your interview</a>" in html and "/join/" in html
    assert "<td" in html and "Date and time" in html and "**" not in html
    with SessionLocal() as db:
        session = db.scalar(
            select(InterviewSession).where(
                InterviewSession.candidate_id == screened["Alex"]
            )
        )
        assert session.invitation_status == InvitationStatus.SENT


def test_without_a_template_the_standard_text_is_used(screened, mailbox):
    checked, _ = invite(screened, screened["Alex"])

    assert checked.email["template"] == emails.STANDARD_NAME
    assert mailbox.sent[0]["subject"] == "Interview invitation: PHP Developer"


def test_a_failed_email_keeps_the_interview(screened, mailbox):
    mailbox.fail = "The email address was refused."

    _, results = invite(screened, screened["Alex"], screened["Cam"])

    assert [r["done"] for r in results] == [True, True]  # both interviews saved
    assert results[0]["email"] == "The email address was refused."
    assert results[1]["email"] == "No email address."  # Cam has none
    with SessionLocal() as db:
        statuses = db.scalars(
            select(InterviewSession.invitation_status).where(
                InterviewSession.job_id == screened["job_id"]
            )
        ).all()
    assert statuses == [InvitationStatus.FAILED, InvitationStatus.FAILED]


def test_send_again_from_the_interviews_page(screened, client, mailbox):
    headers = {
        "Authorization": f"Bearer {create_access_token(screened['user_id'], Role.INTERVIEWER)}"
    }
    mailbox.fail = "The email service could not be reached."
    invite(screened, screened["Alex"])
    mailbox.fail = None
    upcoming = client.get("/api/interviews", headers=headers).json()
    (interview,) = [i for i in upcoming if i["job_id"] == screened["job_id"]]

    answer = client.post(
        f"/api/interviews/{interview['id']}/send", headers=headers
    ).json()

    assert answer == {"sent": True, "message": "Invitation sent"}
    link = mailbox.sent[-1]["text"].split("/join/")[1].split()[0]
    assert (
        client.post("/api/auth/candidate", json={"link_token": link}).status_code == 200
    )


def test_html_is_escaped_and_the_link_always_included(screened):
    with SessionLocal() as db:
        candidate = db.get(Candidate, screened["Alex"])
        candidate.full_name = "Alex <b>Strong</b>"
        job = db.get(Job, screened["job_id"])
        no_link = (
            "Subject: Hi {candidate_name}\n\nHello {candidate_name}, see you soon."
        )
        email = emails.compose(
            no_link, candidate, job, clock.now(), 45, "https://app.example.com/join/t"
        )

    assert "<b>Strong</b>" not in email.html and "&lt;b&gt;Strong" in email.html
    assert "Your personal link: https://app.example.com/join/t" in email.text
    assert 'href="https://app.example.com/join/t"' in email.html
