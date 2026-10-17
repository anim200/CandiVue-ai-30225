r"""LangGraph 1: the Hiring Assistant (Figure 3): prepare the job, then
shortlist and invite candidates.

    START -> load_context -> assistant --(tool call)--> tools --> assistant ...
                                       \--(reply)-----> END
             tools --(a JD was written)--> human_review (interrupt)
             human_review --approve--> confirm_posting (interrupt)
             human_review --reject---> assistant (writes a new version)
             human_review --edit-----> human_review (new version to approve)
             confirm_posting --post---> post_to_job_board --> END
             confirm_posting --skip---> END (job stays unposted)
             tools --(request_job_posting)--> confirm_posting (ask again later)
             tools --(invitations planned)--> confirm_invitations (interrupt)
             confirm_invitations --> END (saved, or nothing done)

- The LLM ("assistant") decides which tool to call; RAG only if useful.
- human_review PAUSES the graph (LangGraph interrupt) until the interviewer
  approves, edits or rejects the JD (§4B-7). The paused state is saved by the
  checkpointer, so it survives a restart (N26).
- confirm_posting PAUSES again and asks "Post this job to the job board?".
  Only the interviewer's "Post" click publishes it.
- confirm_invitations PAUSES with the checked plan (invite, reschedule or
  cancel interviews); nothing is saved until the interviewer confirms
  (§4B-7b), and everything is checked again at that moment.
- One thread per job: thread_id "assistant-job-<id>".
- Interview room mode (§4B-10): the same graph helps during a live interview
  with its own thread per interview, "assistant-interview-<session id>"
  (session_id in the state). It then gets only the room tools (question
  bank, CV questions, CV summary, rag_search) and the room instructions; a
  job chat waiting for a confirmation never blocks it. No interrupts here.
- Retry path (§8.2): a tool call with invalid arguments is sent back to the
  LLM as an error message so it can correct itself.
- After posting, skipping or confirming invitations the turn ends without
  another AI request: the chat card already shows the result (fewer
  requests on the free tier, README "AI usage").
"""

import logging
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolInvocationError
from langgraph.types import interrupt
from pydantic import ValidationError
from sqlalchemy import select

from app.ai.llm import invoke_llm
from app.assistant import posting
from app.assistant.prompts import ASSISTANT_PROMPT, ROOM_PROMPT
from app.assistant.room_tools import ROOM_TOOLS, question_bank_size
from app.assistant.schemas import JobDescriptionContent
from app.assistant.tools import TOOLS, rag_search
from app.core import clock
from app.db.database import SessionLocal
from app.db.models import InterviewSession, Job, JobDescription
from app.db.models.job import JobBoardStatus, JobDescriptionStatus, JobStatus
from app.interviews import planning
from app.runs.runner import graph_config

logger = logging.getLogger(__name__)

THREAD_KIND = "assistant-job"
ROOM_THREAD_KIND = "assistant-interview"
MAX_STEPS = 30  # safety limit for one chat turn (stops endless tool loops)
ROOM_TOOLSET = [*ROOM_TOOLS, rag_search]  # what the LLM may call in the room
# Every tool the graph can run (each once, by name).
ALL_TOOLS = list({t.name: t for t in [*TOOLS, *ROOM_TOOLSET]}.values())


class AssistantState(MessagesState):
    """What the graph carries between steps: the chat messages (from
    MessagesState), the job and the interviewer chatting, a context summary
    and the last review action."""

    job_id: int
    interviewer_id: int
    session_id: int | None  # set in the interview room
    context: str
    review_action: str | None


def thread_config(job_id: int) -> dict:
    """LangGraph config for a job's chat thread (same thread after a restart)."""
    config = graph_config(THREAD_KIND, job_id)
    config["recursion_limit"] = MAX_STEPS
    return config


def room_thread_config(session_id: int) -> dict:
    """LangGraph config for an interview's assistant thread (the room)."""
    config = graph_config(ROOM_THREAD_KIND, session_id)
    config["recursion_limit"] = MAX_STEPS
    return config


def load_context(state: AssistantState) -> dict:
    """Read the job, its saved profile and latest JD, as a summary for the LLM."""
    if state.get("session_id"):
        return {"context": room_context(state["session_id"]), "review_action": None}
    with SessionLocal() as db:
        job = db.get(Job, state["job_id"])
        latest = db.scalar(
            select(JobDescription)
            .where(JobDescription.job_id == job.id)
            .order_by(JobDescription.version.desc())
            .limit(1)
        )
        profile = job.profile or "none saved yet"
        jd = (
            f"version {latest.version} ({latest.status.value})"
            if latest
            else "none yet"
        )
        closes = job.applications_close_at
        deadline = clock.local_text(closes) if closes else "not set yet"
        return {
            "context": (
                f"Now: {clock.local_text(clock.now())} ({clock.local_zone().key})\n"
                f"Current job: {job.title}\nSaved profile: {profile}\nLatest JD: {jd}\n"
                f"Applications close: {deadline}"
            ),
            "review_action": None,
        }


def room_context(session_id: int) -> str:
    """What the LLM knows about the interview in the room. The candidate's
    name is left out; CV facts come only through the tools (reduced)."""
    with SessionLocal() as db:
        session = db.get(InterviewSession, session_id)
        job = db.get(Job, session.job_id)
        requirements = "; ".join(
            f"{r['text']} ({r['level']})"
            for r in (job.profile or {}).get("requirements", [])
        )
        bank = question_bank_size(db)
        return (
            f"Now: {clock.local_text(clock.now())} ({clock.local_zone().key})\n"
            f"Interview for the job: {job.title}\n"
            f"Job requirements: {requirements or 'none saved'}\n"
            f"Scheduled: {clock.local_text(session.scheduled_at)}, "
            f"{session.duration_minutes} minutes\n"
            f"Question bank documents: {bank}{' (empty)' if bank == 0 else ''}\n"
            "CV questions already made for this interview: "
            + ("yes" if session.cv_questions else "no")
        )


def assistant(state: AssistantState) -> dict:
    """The LLM reads the chat and decides: reply, or call a tool. In the
    interview room it gets the room instructions and tools only."""
    room = bool(state.get("session_id"))
    instructions = ROOM_PROMPT if room else ASSISTANT_PROMPT
    tools = ROOM_TOOLSET if room else TOOLS
    prompt = [
        SystemMessage(f"{instructions}\n\n{state['context']}"),
        *state["messages"],
    ]
    answer = invoke_llm(prompt, prepare=lambda model: model.bind_tools(tools))
    return {"messages": [answer]}


def after_assistant(state: AssistantState) -> str:
    """Go to the tools if the LLM asked for one; otherwise the turn ends."""
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else END


def after_tools(state: AssistantState) -> str:
    """After a new JD draft, pause for the interviewer; after a request to
    post, ask the interviewer to confirm; otherwise back to the LLM."""
    for message in reversed(state["messages"]):
        if not isinstance(message, ToolMessage):
            break
        kind = (message.artifact or {}).get("kind")
        if kind == "jd":
            return "human_review"
        if kind == "post_request":
            return "confirm_posting"
        if kind == "interview_plan":
            return "confirm_invitations"
    return "assistant"


def human_review(state: AssistantState) -> dict:
    """Pause until the interviewer approves, edits or rejects the latest draft."""
    with SessionLocal() as db:
        draft = db.scalar(
            select(JobDescription)
            .where(
                JobDescription.job_id == state["job_id"],
                JobDescription.status == JobDescriptionStatus.DRAFT,
            )
            .order_by(JobDescription.version.desc())
            .limit(1)
        )
        if draft is None:
            return {"review_action": None}
        draft_id, version = draft.id, draft.version

    # The graph stops here and is saved. It continues when the API resumes it
    # with the interviewer's decision (Command(resume=...)).
    decision = interrupt({"kind": "jd_approval", "jd_id": draft_id, "version": version})

    action = decision["action"]
    new_jd_id = None  # set when an edit creates a new version
    with SessionLocal() as db:
        draft = db.get(JobDescription, draft_id)
        job = db.get(Job, state["job_id"])
        if action == "approve":
            draft.status = JobDescriptionStatus.APPROVED
            draft.approved_at = datetime.now(UTC)
            job.status = JobStatus.OPEN
            note = f"I approved job description version {version}."
        elif action == "reject":
            draft.status = JobDescriptionStatus.REJECTED
            draft.reviewer_feedback = decision["feedback"]
            note = (
                f"I rejected job description version {version}. "
                f"Please write a new version. Feedback: {decision['feedback']}"
            )
        else:  # edit: the interviewer's text becomes a new version to approve
            content = JobDescriptionContent.model_validate(decision["content"])
            draft.status = JobDescriptionStatus.REJECTED
            draft.reviewer_feedback = "Replaced by the interviewer's edited version."
            edited = JobDescription(
                job_id=job.id,
                version=version + 1,
                content=content.model_dump_json(),
                sources=draft.sources,
            )
            db.add(edited)
            db.flush()  # gives the new version its id
            new_jd_id = edited.id
            note = (
                f"I edited the job description; it is saved as version {version + 1}."
            )
        db.commit()
    logger.info("JD review: job %d, version %d, %s", state["job_id"], version, action)
    # Shown in the chat as a review note (marked so the screen can style it).
    # The new version's id lets the screen show it as a card to approve.
    marks = {"review": action, "jd_id": new_jd_id} if new_jd_id else {"review": action}
    return {
        "messages": [HumanMessage(note, additional_kwargs=marks)],
        "review_action": action,
    }


def after_review(state: AssistantState) -> str:
    """An edit needs approval again; after an approval the interviewer is
    asked whether to post; a rejection goes back to the LLM for a new version."""
    action = state["review_action"]
    if action == "edit":
        return "human_review"
    return "confirm_posting" if action == "approve" else "assistant"


def confirm_posting(state: AssistantState) -> dict:
    """Pause and ask "Post this job to the job board?" (Post / Don't post)."""
    with SessionLocal() as db:
        job = db.get(Job, state["job_id"])
        approved = db.scalar(
            select(JobDescription)
            .where(
                JobDescription.job_id == job.id,
                JobDescription.status == JobDescriptionStatus.APPROVED,
            )
            .order_by(JobDescription.version.desc())
            .limit(1)
        )
        if approved is None:
            return {"review_action": None}
        # Shown as "Post to job board?" in the job list while we wait.
        job.job_board_status = JobBoardStatus.AWAITING_CONFIRMATION
        db.commit()
        question = {
            "kind": "post_confirmation",
            "jd_id": approved.id,
            "version": approved.version,
            "has_form": bool(job.google_form_url),
        }

    # The graph stops here until the interviewer clicks Post or Don't post.
    decision = interrupt(question)

    action = decision["action"]  # "post" or "skip"
    with SessionLocal() as db:
        # post_job() records the outcome; "skip" leaves the job unposted.
        db.get(Job, state["job_id"]).job_board_status = JobBoardStatus.NOT_POSTED
        db.commit()
    note = (
        "Post it to the job board."
        if action == "post"
        else "Don't post it now. I will ask you later."
    )
    logger.info("Posting decision: job %d, %s", state["job_id"], action)
    return {
        "messages": [HumanMessage(note, additional_kwargs={"review": action})],
        "review_action": action,
    }


def after_confirm(state: AssistantState) -> str:
    """Post only when the interviewer chose "Post"; otherwise the turn ends
    (the job stays unposted until they ask)."""
    return "post_to_job_board" if state["review_action"] == "post" else END


def confirm_invitations(state: AssistantState) -> dict:
    """Pause until the interviewer confirms (possibly after changing times or
    leaving people out) or cancels the planned interviews; then save them."""
    plan = next(
        m.artifact
        for m in reversed(state["messages"])
        if isinstance(m, ToolMessage)
        and (m.artifact or {}).get("kind") == "interview_plan"
    )
    # The graph stops here until the interviewer answers on the card.
    decision = interrupt({**plan, "kind": "invitation_confirmation"})

    if decision["action"] == "cancel":
        note = "I cancelled this. Nothing was saved."
        return {
            "messages": [HumanMessage(note, additional_kwargs={"review": "cancel"})]
        }
    with SessionLocal() as db:
        checked = planning.make_plan(
            db,
            state["job_id"],
            state["interviewer_id"],
            plan["action"],
            decision["items"],
            plan["duration"],
            plan["invite_again"],
        )
        results = planning.apply(db, checked, state["job_id"], state["interviewer_id"])
    done = sum(r["done"] for r in results)
    skipped = "; ".join(f"{r['name']}: {r['reason']}" for r in results if not r["done"])
    unsent = "; ".join(
        f"{r['name']}: {r['email']}"
        for r in results
        if r["email"] not in (None, "sent")
    )
    no_calendar = "; ".join(
        f"{r['name']}: {r['calendar']}"
        for r in results
        if r["calendar"] not in (None, "added", "moved", "removed")
    )
    note = f"I confirmed ({plan['action']}): {done} done."
    note += f" Skipped: {skipped}." if skipped else ""
    note += f" Emails not sent: {unsent}." if unsent else ""
    note += f" Calendar not updated: {no_calendar}." if no_calendar else ""
    logger.info("Interviews %s: job %d, %d done", plan["action"], state["job_id"], done)
    marks = {"invitations": {"action": plan["action"], "results": results}}
    return {"messages": [HumanMessage(note, additional_kwargs=marks)]}


def posting_message(result: dict) -> HumanMessage:
    """A chat note with the job board result (marked so the screen shows a card)."""
    text = {
        "posted": f"The job board accepted the post: {result['url']}",
        "needs_form": "The job was not posted: the application form link is missing.",
    }.get(
        result["status"], f"The job board did not accept the post: {result['message']}"
    )
    return HumanMessage(text, additional_kwargs={"posting": result})


def post_to_job_board(state: AssistantState) -> dict:
    """Approval tool (Figure 3): publish the approved JD on the job board via
    MCP. Runs only after the interviewer approved; a failure keeps the JD."""
    return {"messages": [posting_message(posting.post_job(state["job_id"]))]}


def build_hiring_assistant(checkpointer):
    """Assemble and compile the graph with the database checkpointer."""
    graph = StateGraph(AssistantState)
    graph.add_node("load_context", load_context)
    graph.add_node("assistant", assistant)
    # Invalid tool arguments go back to the LLM as an error (retry path);
    # an AI outage (AIServiceError) is not caught and becomes a clear 503.
    graph.add_node(
        "tools",
        ToolNode(
            ALL_TOOLS,
            handle_tool_errors=(ToolInvocationError, ValidationError, ValueError),
        ),
    )
    graph.add_node("human_review", human_review)
    graph.add_node("confirm_posting", confirm_posting)
    graph.add_node("post_to_job_board", post_to_job_board)
    graph.add_node("confirm_invitations", confirm_invitations)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "assistant")
    graph.add_conditional_edges("assistant", after_assistant, ["tools", END])
    graph.add_conditional_edges(
        "tools",
        after_tools,
        ["human_review", "confirm_posting", "confirm_invitations", "assistant"],
    )
    graph.add_conditional_edges(
        "human_review", after_review, ["human_review", "confirm_posting", "assistant"]
    )
    graph.add_conditional_edges(
        "confirm_posting", after_confirm, ["post_to_job_board", END]
    )
    graph.add_edge("post_to_job_board", END)
    graph.add_edge("confirm_invitations", END)
    return graph.compile(checkpointer=checkpointer)
