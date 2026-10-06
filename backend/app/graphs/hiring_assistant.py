r"""LangGraph 1: the Hiring Assistant (Figure 3), part 1 "Prepare the job".

    START -> load_context -> assistant --(tool call)--> tools --> assistant ...
                                       \--(reply)-----> END
             tools --(a JD was written)--> human_review (interrupt)
             human_review --approve--> post_to_job_board --> assistant
             human_review --reject---> assistant (writes a new version)
             human_review --edit-----> human_review (new version to approve)

- The LLM ("assistant") decides which tool to call; RAG only if useful.
- human_review PAUSES the graph (LangGraph interrupt) until the interviewer
  approves, edits or rejects the JD (§4B-7). The paused state is saved by the
  checkpointer, so it survives a restart (N26).
- One thread per job: thread_id "assistant-job-<id>".
- Retry path (§8.2): a tool call with invalid arguments is sent back to the
  LLM as an error message so it can correct itself.
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

from app.ai.llm import get_chat_model, invoke_llm
from app.assistant import posting
from app.assistant.prompts import ASSISTANT_PROMPT
from app.assistant.schemas import JobDescriptionContent
from app.assistant.tools import TOOLS
from app.db.database import SessionLocal
from app.db.models import Job, JobDescription
from app.db.models.job import JobDescriptionStatus, JobStatus
from app.runs.runner import graph_config

logger = logging.getLogger(__name__)

THREAD_KIND = "assistant-job"
MAX_STEPS = 30  # safety limit for one chat turn (stops endless tool loops)


class AssistantState(MessagesState):
    """What the graph carries between steps: the chat messages (from
    MessagesState), the job, a context summary and the last review action."""

    job_id: int
    context: str
    review_action: str | None


def thread_config(job_id: int) -> dict:
    """LangGraph config for a job's chat thread (same thread after a restart)."""
    config = graph_config(THREAD_KIND, job_id)
    config["recursion_limit"] = MAX_STEPS
    return config


def load_context(state: AssistantState) -> dict:
    """Read the job, its saved profile and latest JD, as a summary for the LLM."""
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
        return {
            "context": f"Current job: {job.title}\nSaved profile: {profile}\nLatest JD: {jd}",
            "review_action": None,
        }


def assistant(state: AssistantState) -> dict:
    """The LLM reads the chat and decides: reply, or call a tool."""
    model = get_chat_model().bind_tools(TOOLS)
    prompt = [
        SystemMessage(f"{ASSISTANT_PROMPT}\n\n{state['context']}"),
        *state["messages"],
    ]
    return {"messages": [invoke_llm(prompt, model=model)]}


def after_assistant(state: AssistantState) -> str:
    """Go to the tools if the LLM asked for one; otherwise the turn ends."""
    last = state["messages"][-1]
    return "tools" if isinstance(last, AIMessage) and last.tool_calls else END


def after_tools(state: AssistantState) -> str:
    """After a new JD draft, pause for the interviewer; otherwise back to the LLM."""
    for message in reversed(state["messages"]):
        if not isinstance(message, ToolMessage):
            break
        if (message.artifact or {}).get("kind") == "jd":
            return "human_review"
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
    """An edit needs approval again; an approval is posted; a rejection goes
    back to the LLM for a new version."""
    action = state["review_action"]
    if action == "edit":
        return "human_review"
    return "post_to_job_board" if action == "approve" else "assistant"


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
            TOOLS, handle_tool_errors=(ToolInvocationError, ValidationError, ValueError)
        ),
    )
    graph.add_node("human_review", human_review)
    graph.add_node("post_to_job_board", post_to_job_board)

    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "assistant")
    graph.add_conditional_edges("assistant", after_assistant, ["tools", END])
    graph.add_conditional_edges("tools", after_tools, ["human_review", "assistant"])
    graph.add_conditional_edges(
        "human_review", after_review, ["human_review", "post_to_job_board", "assistant"]
    )
    graph.add_edge("post_to_job_board", "assistant")
    return graph.compile(checkpointer=checkpointer)
