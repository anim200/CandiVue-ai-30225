"""Turns a saved chat thread into simple items for the screen.

LangGraph stores LangChain messages; the screen needs plain items such as
"user message", "assistant message", "profile card", "JD card", "step",
"review note", "shortlist card" or "interview results". JD cards are read
fresh from the database, so they always show the current status (e.g. a
rejected version says so).
"""

import json

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from sqlalchemy.orm import Session

from app.db.models import JobDescription

# How each tool appears as a small "step" line in the chat.
STEP_TEXT = {
    "save_job_profile": "Saved the job profile",
    "write_job_description": "Wrote a job description draft",
}


def message_text(message) -> str:
    """Get the plain text of a message (some models send a list of parts)."""
    if isinstance(message.content, str):
        return message.content
    return "".join(
        part.get("text", "") for part in message.content if isinstance(part, dict)
    )


def jd_card(jd: JobDescription) -> dict:
    """The data the JD approval card shows."""
    return {
        "id": jd.id,
        "version": jd.version,
        "status": jd.status.value,
        "content": json.loads(jd.content),
        "sources": jd.sources,
        "feedback": jd.reviewer_feedback,
        "approved_at": jd.approved_at.isoformat() if jd.approved_at else None,
    }


def thread_items(db: Session, messages: list) -> list[dict]:
    """Convert the stored messages into screen items, in order."""
    items = []
    last_profile = None  # the model sometimes saves the same profile twice
    for message in messages:
        if isinstance(message, HumanMessage) and message.additional_kwargs.get(
            "posting"
        ):
            items.append({"kind": "posting", **message.additional_kwargs["posting"]})
            continue
        if isinstance(message, HumanMessage) and message.additional_kwargs.get(
            "invitations"
        ):
            done = message.additional_kwargs["invitations"]
            items.append({"kind": "invitations", **done})
            continue
        if isinstance(message, HumanMessage):
            review = message.additional_kwargs.get("review")
            kind = "review" if review else "user"
            items.append(
                {"kind": kind, "text": message_text(message), "action": review}
            )
            # An edit creates a new version directly: show it as a JD card.
            edited = db.get(JobDescription, message.additional_kwargs.get("jd_id") or 0)
            if review == "edit" and edited is not None:
                items.append({"kind": "jd", "jd": jd_card(edited)})
        elif isinstance(message, AIMessage):
            text = message_text(message).strip()
            if text:
                items.append({"kind": "assistant", "text": text})
        elif isinstance(message, ToolMessage):
            artifact = message.artifact or {}
            kind = artifact.get("kind")
            if kind == "post_request":
                items.append({"kind": "step", "text": "Asked you to confirm the post"})
            elif kind == "profile" and artifact["profile"] != last_profile:
                last_profile = artifact["profile"]
                items.append({"kind": "step", "text": STEP_TEXT["save_job_profile"]})
                items.append(
                    {
                        "kind": "profile",
                        "profile": artifact["profile"],
                        "weights": artifact.get("weights"),
                    }
                )
            elif kind == "form":
                items.append(
                    {"kind": "step", "text": "Saved the application form link"}
                )
            elif kind == "deadline":
                text = f"Applications close on {artifact['when']}"
                items.append({"kind": "step", "text": text})
            elif kind == "shortlist":
                items.append({"kind": "step", "text": "Updated the shortlist"})
                items.append(artifact)
            elif kind == "slots":
                text = f"Found {len(artifact['times'])} free interview times"
                items.append({"kind": "step", "text": text})
            elif kind == "interview_plan":
                text = "Prepared the interviews for your confirmation"
                items.append({"kind": "step", "text": text})
            elif kind == "rag":
                count = len(artifact.get("passages", []))
                items.append(
                    {
                        "kind": "step",
                        "text": f"Looked at {count} passages in the knowledge base",
                    }
                )
            elif kind == "jd":
                jd = db.get(JobDescription, artifact["jd_id"])
                if jd is not None:
                    items.append(
                        {"kind": "step", "text": STEP_TEXT["write_job_description"]}
                    )
                    items.append({"kind": "jd", "jd": jd_card(jd)})
    return items
