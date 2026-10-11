"""Hiring Assistant graph and API (LangGraph 1, up to JD approval).

A scripted fake LLM plays back fixed answers (tool calls or text), so the
real graph, database and checkpointer are used without any AI provider.
Runs inside Docker; everything created is deleted afterwards.
"""

from datetime import UTC, datetime

import pytest
from helpers import call
from langchain_core.messages import AIMessage
from sqlalchemy import select

from app.assistant import drafting, tools
from app.assistant.schemas import JobDescriptionContent
from app.db.database import SessionLocal
from app.db.models import Job, JobDescription
from app.db.models.job import JobDescriptionStatus, JobStatus
from app.db.models.knowledge import KnowledgeCollection
from app.knowledge.search import Passage

pytestmark = pytest.mark.usefixtures("database_available")

PROFILE = {
    "title": "Sample Job: Python Backend Developer",
    "min_years_experience": 3,
    "requirements": [
        {"text": "Python web framework", "level": "mandatory", "category": "skill"},
        {"text": "PostgreSQL", "level": "required", "category": "skill"},
        {"text": "Cloud deployment", "level": "preferred", "category": "skill"},
    ],
}
JD = {
    "title": "Python Backend Developer",
    "about": "Build and maintain REST services for internal platforms.",
    "responsibilities": ["Design PostgreSQL schemas", "Write tested FastAPI code"],
}


@pytest.fixture
def drafts(monkeypatch):
    """Fake JD writer: records the feedback it was given, returns a fixed JD."""
    calls = []

    def fake_draft(profile, passages, feedback=None, notes=None):
        """Remember the inputs and return the sample JD."""
        calls.append({"passages": passages, "feedback": feedback})
        return JobDescriptionContent.model_validate(JD)

    monkeypatch.setattr(drafting, "draft_job_description", fake_draft)
    return calls


def new_job(client, headers) -> int:
    """Create a job through the API and return its id."""
    response = client.post("/api/jobs", headers=headers)
    assert response.status_code == 201
    return response.json()["id"]


def say(client, headers, job_id, text="I need a Python backend developer."):
    """Send a chat message to the assistant."""
    return client.post(
        f"/api/assistant/jobs/{job_id}/messages", headers=headers, json={"text": text}
    )


def review(client, headers, job_id, **decision):
    """Send the interviewer's JD decision."""
    return client.post(
        f"/api/assistant/jobs/{job_id}/review", headers=headers, json=decision
    )


def decide(client, headers, job_id, action):
    """Answer "Post this job to the job board?" ("post" or "skip")."""
    return client.post(
        f"/api/assistant/jobs/{job_id}/post-decision",
        headers=headers,
        json={"action": action},
    )


def load_jds(job_id) -> list[JobDescription]:
    """All JD versions of a job, oldest first."""
    with SessionLocal() as db:
        return list(
            db.scalars(
                select(JobDescription)
                .where(JobDescription.job_id == job_id)
                .order_by(JobDescription.version)
            )
        )


def test_new_job_starts_as_draft_profile(client, headers):
    job = client.post("/api/jobs", headers=headers).json()

    assert job["title"] == "New job"
    assert job["stage"] == "drafting_profile"
    assert any(
        j["id"] == job["id"] for j in client.get("/api/jobs", headers=headers).json()
    )


def test_profile_then_jd_pauses_for_review_then_approve(
    client, headers, scripted, drafts
):
    job_id = new_job(client, headers)
    scripted += [
        call("save_job_profile", {"profile": PROFILE}),
        call("write_job_description", {}),
        AIMessage(content="Thanks, the job description is approved."),
    ]

    thread = say(client, headers, job_id).json()

    # The graph stopped at human_review and waits for the interviewer.
    assert thread["pending_review"]["kind"] == "jd_approval"
    kinds = [item["kind"] for item in thread["items"]]
    assert kinds == ["user", "step", "profile", "step", "jd"]
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.title == PROFILE["title"]
        assert job.profile["requirements"][0]["level"] == "mandatory"

    thread = review(client, headers, job_id, action="approve").json()

    # After approval the graph pauses again and asks whether to post.
    assert thread["pending_review"]["kind"] == "post_confirmation"
    assert thread["items"][-1]["kind"] == "review"
    (jd,) = load_jds(job_id)
    assert jd.status == JobDescriptionStatus.APPROVED and jd.approved_at is not None
    with SessionLocal() as db:
        assert db.get(Job, job_id).status == JobStatus.OPEN
    job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
    assert job["stage"] == "post_to_confirm"

    thread = decide(client, headers, job_id, "skip").json()

    # "Don't post": nothing is posted; the assistant answers.
    assert thread["pending_review"] is None
    assert [i["kind"] for i in thread["items"][-2:]] == ["review", "assistant"]
    assert thread["items"][-2]["action"] == "skip"
    assert not [i for i in thread["items"] if i["kind"] == "posting"]
    job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
    assert job["stage"] == "jd_approved"


def test_reject_rewrites_with_the_feedback(client, headers, scripted, drafts):
    job_id = new_job(client, headers)
    scripted += [
        call("save_job_profile", {"profile": PROFILE}),
        call("write_job_description", {}),
    ]
    say(client, headers, job_id)
    scripted += [
        call("write_job_description", {}, "c2")
    ]  # the LLM rewrites after rejection

    thread = review(
        client,
        headers,
        job_id,
        action="reject",
        feedback="Too long, mention hybrid work.",
    ).json()

    assert drafts[-1]["feedback"] == "Too long, mention hybrid work."
    assert thread["pending_review"]["version"] == 2
    v1, v2 = load_jds(job_id)
    assert (
        v1.status == JobDescriptionStatus.REJECTED
        and v2.status == JobDescriptionStatus.DRAFT
    )


def test_edit_saves_a_new_version_that_still_needs_approval(
    client, headers, scripted, drafts
):
    job_id = new_job(client, headers)
    scripted += [
        call("save_job_profile", {"profile": PROFILE}),
        call("write_job_description", {}),
    ]
    say(client, headers, job_id)
    edited = {**JD, "about": "An edited description of the role and the team."}

    thread = review(client, headers, job_id, action="edit", content=edited).json()

    assert thread["pending_review"]["version"] == 2  # paused again: approve first
    # The edited version appears in the chat as a card to approve.
    last = thread["items"][-1]
    assert last["kind"] == "jd" and last["jd"]["version"] == 2
    assert last["jd"]["id"] == thread["pending_review"]["jd_id"]
    v1, v2 = load_jds(job_id)
    assert v1.status == JobDescriptionStatus.REJECTED
    assert (
        v2.status == JobDescriptionStatus.DRAFT and "edited description" in v2.content
    )


def test_rag_passages_become_jd_sources(client, headers, scripted, drafts, monkeypatch):
    passage = Passage(
        1,
        "hybrid-work.txt",
        KnowledgeCollection.COMPANY_POLICIES,
        "Hybrid: 2 days at home.",
        0.9,
    )
    monkeypatch.setattr(tools, "search_knowledge", lambda db, q, c, n: [passage])
    job_id = new_job(client, headers)
    scripted += [
        call("rag_search", {"query": "work policy"}),
        call("save_job_profile", {"profile": PROFILE}, "c2"),
        call("write_job_description", {}, "c3"),
    ]

    thread = say(client, headers, job_id).json()

    assert drafts[-1]["passages"] == ["Hybrid: 2 days at home."]
    jd = thread["items"][-1]["jd"]
    assert jd["sources"] == [
        {
            "document_id": 1,
            "filename": "hybrid-work.txt",
            "collection": "company_policies",
        }
    ]


def test_invalid_tool_arguments_go_back_to_the_llm(client, headers, scripted, drafts):
    job_id = new_job(client, headers)
    bad_profile = {**PROFILE, "requirements": []}  # at least one requirement is needed
    scripted += [
        call("save_job_profile", {"profile": bad_profile}),
        AIMessage(content="Which requirements should the job have?"),
    ]

    thread = say(client, headers, job_id).json()

    # Retry path: the error went back to the LLM, which asked a question.
    assert thread["items"][-1]["text"] == "Which requirements should the job have?"
    assert thread["pending_review"] is None
    with SessionLocal() as db:
        assert not db.get(Job, job_id).profile


def test_chat_waits_until_the_review_is_done(client, headers, scripted, drafts):
    job_id = new_job(client, headers)
    scripted += [
        call("save_job_profile", {"profile": PROFILE}),
        call("write_job_description", {}),
    ]
    say(client, headers, job_id)

    response = say(client, headers, job_id, "Another message")

    assert response.status_code == 409


def test_review_needs_something_to_review(client, headers):
    job_id = new_job(client, headers)

    assert review(client, headers, job_id, action="approve").status_code == 409


def test_reject_needs_feedback(client, headers):
    job_id = new_job(client, headers)

    assert (
        review(client, headers, job_id, action="reject", feedback=" ").status_code
        == 422
    )


def test_ai_outage_gives_a_clear_503(client, headers, scripted):
    job_id = new_job(client, headers)
    scripted += [TimeoutError("model did not answer")] * 5

    response = say(client, headers, job_id)

    assert response.status_code == 503
    assert "unavailable" in response.json()["detail"]


def test_long_messages_are_refused(client, headers):
    job_id = new_job(client, headers)

    assert say(client, headers, job_id, "x" * 2001).status_code == 422


def test_try_again_continues_the_saved_turn(client, headers, scripted):
    job_id = new_job(client, headers)
    scripted += [TimeoutError("model did not answer")] * 3  # first + 2 retries fail
    assert say(client, headers, job_id).status_code == 503

    scripted += [AIMessage(content="What are the must-have skills?")]
    thread = client.post(f"/api/assistant/jobs/{job_id}/retry", headers=headers).json()

    kinds = [item["kind"] for item in thread["items"]]
    assert kinds == ["user", "assistant"]  # the message was kept, not sent twice
    assert thread["items"][-1]["text"] == "What are the must-have skills?"


def test_a_never_ending_turn_is_stopped_with_a_clear_message(client, headers, scripted):
    job_id = new_job(client, headers)
    endless = {"profile": PROFILE}
    scripted += [call("save_job_profile", endless, f"c{i}") for i in range(40)]

    response = say(client, headers, job_id)

    assert response.status_code == 503
    assert response.json()["detail"].startswith("The assistant couldn't finish")


def test_rag_search_widens_to_all_collections_when_nothing_found(monkeypatch):
    passage = Passage(
        7,
        "policy.txt",
        KnowledgeCollection.REFERENCE_LIBRARY,
        "Hybrid: 2 days at home.",
        0.8,
    )
    searched = []

    def fake_search(db, query, collections, limit):
        """Only finds the passage when no collection filter is given."""
        searched.append(collections)
        return [] if collections else [passage]

    monkeypatch.setattr(tools, "search_knowledge", fake_search)

    _content, artifact = tools.rag_search.func(
        "hybrid work", [KnowledgeCollection.COMPANY_POLICIES]
    )

    assert searched == [[KnowledgeCollection.COMPANY_POLICIES], None]
    assert artifact["passages"][0]["filename"] == "policy.txt"


FORM_URL = "https://forms.gle/SyntheticTestForm"


@pytest.fixture
def job_board(monkeypatch):
    """Fake job board: records posts; set .fail to make it refuse."""
    from app.assistant import posting
    from app.integrations.job_board import JobBoardError

    board = type("Board", (), {"posts": [], "updates": [], "fail": False})()

    def publish(title, html, labels):
        """Accept the post (or refuse it when .fail is set)."""
        if board.fail:
            raise JobBoardError("The job board refused the post (HTTP 403).")
        board.posts.append((title, html))
        return {"post_id": "1", "url": "https://example.blogspot.com/p/job.html"}

    def update(post_id, title, html):
        """Record an update of an existing post."""
        board.updates.append((post_id, html))
        return {"post_id": post_id, "url": "https://example.blogspot.com/p/job.html"}

    monkeypatch.setattr(posting, "publish_job_post", publish)
    monkeypatch.setattr(posting, "update_job_post", update)
    return board


def approved_flow(client, headers, scripted, form=True):
    """Chat until a JD waits for review (optionally saving the form link)."""
    job_id = new_job(client, headers)
    scripted += [call("save_job_profile", {"profile": PROFILE})]
    if form:
        scripted += [call("save_application_form", {"form_url": FORM_URL}, "cf")]
    scripted += [call("write_job_description", {}, "cw")]
    say(client, headers, job_id)
    return job_id


def test_approve_posts_the_job_to_the_board(
    client, headers, scripted, drafts, job_board
):
    job_id = approved_flow(client, headers, scripted)
    scripted += [AIMessage(content="Your job is posted.")]
    review(client, headers, job_id, action="approve")
    assert job_board.posts == []  # nothing is posted before "Post"

    thread = decide(client, headers, job_id, "post").json()

    posting_items = [i for i in thread["items"] if i["kind"] == "posting"]
    assert posting_items[-1]["status"] == "posted"
    assert posting_items[-1]["url"] == "https://example.blogspot.com/p/job.html"
    title, html = job_board.posts[0]
    assert title == JD["title"] and FORM_URL in html
    job = client.get(f"/api/jobs/{job_id}", headers=headers).json()
    assert job["stage"] == "posted"
    assert job["job_board_post_url"] == "https://example.blogspot.com/p/job.html"


def test_failed_post_keeps_the_jd_and_can_be_tried_again(
    client, headers, scripted, drafts, job_board
):
    job_id = approved_flow(client, headers, scripted)
    job_board.fail = True
    scripted += [AIMessage(content="Posting failed; the JD is saved.")]
    review(client, headers, job_id, action="approve")

    thread = decide(client, headers, job_id, "post").json()

    assert [i for i in thread["items"] if i["kind"] == "posting"][-1][
        "status"
    ] == "failed"
    assert (
        client.get(f"/api/jobs/{job_id}", headers=headers).json()["stage"]
        == "posting_failed"
    )
    (jd,) = load_jds(job_id)
    assert jd.status == JobDescriptionStatus.APPROVED  # nothing lost

    job_board.fail = False
    thread = client.post(f"/api/assistant/jobs/{job_id}/post", headers=headers).json()

    assert [i for i in thread["items"] if i["kind"] == "posting"][-1][
        "status"
    ] == "posted"
    assert (
        client.get(f"/api/jobs/{job_id}", headers=headers).json()["stage"] == "posted"
    )


def test_without_a_form_link_nothing_is_posted(
    client, headers, scripted, drafts, job_board
):
    job_id = approved_flow(client, headers, scripted, form=False)
    scripted += [AIMessage(content="Please send the Google Form link.")]
    review(client, headers, job_id, action="approve")

    thread = decide(client, headers, job_id, "post").json()

    assert [i for i in thread["items"] if i["kind"] == "posting"][-1][
        "status"
    ] == "needs_form"
    assert job_board.posts == []


def test_a_non_google_form_link_goes_back_to_the_llm(client, headers, scripted, drafts):
    job_id = new_job(client, headers)
    scripted += [
        call("save_application_form", {"form_url": "https://evil.example.com/apply"}),
        AIMessage(
            content="That is not a Google Forms link. Please send the form link."
        ),
    ]

    thread = say(client, headers, job_id).json()

    assert thread["items"][-1]["text"].startswith("That is not a Google Forms link")
    with SessionLocal() as db:
        assert db.get(Job, job_id).google_form_url is None


def test_posting_needs_an_approved_jd(client, headers):
    job_id = new_job(client, headers)

    assert (
        client.post(f"/api/assistant/jobs/{job_id}/post", headers=headers).status_code
        == 409
    )


def test_dont_post_then_ask_in_the_chat_to_post(
    client, headers, scripted, drafts, job_board
):
    job_id = approved_flow(client, headers, scripted)
    scripted += [AIMessage(content="Fine, I will not post it.")]
    review(client, headers, job_id, action="approve")
    decide(client, headers, job_id, "skip")
    scripted += [call("request_job_posting", {}, "cp")]

    thread = say(client, headers, job_id, "Please post the job now.").json()

    # The assistant cannot post by itself: it asks again.
    assert thread["pending_review"]["kind"] == "post_confirmation"
    assert job_board.posts == []
    scripted += [AIMessage(content="It is posted.")]

    thread = decide(client, headers, job_id, "post").json()

    assert [i for i in thread["items"] if i["kind"] == "posting"][-1][
        "status"
    ] == "posted"
    assert len(job_board.posts) == 1


def test_chat_waits_for_the_post_decision(client, headers, scripted, drafts):
    job_id = approved_flow(client, headers, scripted)
    review(client, headers, job_id, action="approve")

    response = say(client, headers, job_id, "Another message")

    assert response.status_code == 409
    assert "Post or Don't post" in response.json()["detail"]


def test_post_decision_needs_a_question(client, headers, scripted, drafts):
    job_id = approved_flow(client, headers, scripted)  # JD waits for review

    assert decide(client, headers, job_id, "post").status_code == 409


def test_asking_to_post_needs_an_approved_jd(client, headers):
    job_id = new_job(client, headers)

    with pytest.raises(ValueError, match="approve one first"):
        tools.request_job_posting.func(job_id)


def test_the_same_profile_saved_twice_is_shown_once():
    from langchain_core.messages import ToolMessage

    from app.assistant.thread_view import thread_items

    saved = ToolMessage(
        "saved", tool_call_id="c1", artifact={"kind": "profile", "profile": PROFILE}
    )

    items = thread_items(None, [saved, saved])

    assert [i["kind"] for i in items] == ["step", "profile"]


def test_profile_weights_are_a_suggestion_unless_the_interviewer_gave_them(
    client, headers
):
    from app.assistant.schemas import JobProfile
    from app.screening.weights import SuggestedWeights

    job_id = new_job(client, headers)
    profile = JobProfile.model_validate(PROFILE)  # as LangChain passes them
    weights = SuggestedWeights(
        skills=40,
        experience=30,
        qualifications=10,
        ats=20,
        reason="Skills matter most for this role.",
    )

    tools.save_job_profile.func(profile, job_id, weights)
    with SessionLocal() as db:
        job = db.get(Job, job_id)
        assert job.ai_weights["skills"] == 40 and job.weights is None

    tools.save_job_profile.func(profile, job_id, weights, weights_from_interviewer=True)
    with SessionLocal() as db:
        assert (
            db.get(Job, job_id).weights["reason"] == "Skills matter most for this role."
        )


def test_the_deadline_is_read_as_local_time(client, headers, scripted):
    job_id = new_job(client, headers)
    scripted += [
        call("set_application_deadline", {"closes_at": "2030-01-15T17:00"}),
        AIMessage(content="Applications close on 15 January 2030."),
    ]

    thread = say(
        client, headers, job_id, "Close applications 15 Jan 2030, 5 pm."
    ).json()

    with SessionLocal() as db:
        closes = db.get(Job, job_id).applications_close_at
    assert closes == datetime(2030, 1, 15, 11, 0, tzinfo=UTC)  # 17:00 in Dhaka
    steps = [item["text"] for item in thread["items"] if item["kind"] == "step"]
    assert steps == ["Applications close on Tue 15 Jan 2030, 17:00"]


def test_a_deadline_in_the_past_goes_back_to_the_llm(client, headers, scripted):
    job_id = new_job(client, headers)
    scripted += [
        call("set_application_deadline", {"closes_at": "2020-01-15T17:00"}),
        AIMessage(content="That date has passed. Which date do you mean?"),
    ]

    say(client, headers, job_id, "Close applications on 15 Jan 2020.")

    with SessionLocal() as db:
        assert db.get(Job, job_id).applications_close_at is None


def test_a_new_deadline_updates_the_posted_job(
    client, headers, scripted, drafts, job_board
):
    job_id = approved_flow(client, headers, scripted)
    scripted += [AIMessage(content="Posted.")]
    review(client, headers, job_id, action="approve")
    decide(client, headers, job_id, "post")
    scripted += [
        call("set_application_deadline", {"closes_at": "2030-01-15T17:00"}),
        AIMessage(content="Done: the post shows the new date."),
    ]

    say(client, headers, job_id, "Applications close 15 Jan 2030 at 5 pm.")

    (post_id, html) = job_board.updates[0]
    assert post_id == "1" and "Applications close on Tue 15 Jan 2030, 17:00" in html
