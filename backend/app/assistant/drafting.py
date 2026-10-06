"""Writes a job description draft with the LLM (used by write_job_description).

The answer must match JobDescriptionContent (structured output); a reply in
another shape is retried and finally fails with a clear error (N6).
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from app.ai.llm import invoke_llm
from app.assistant.prompts import JD_WRITER_PROMPT
from app.assistant.schemas import JobDescriptionContent, JobProfile


def draft_job_description(
    profile: JobProfile,
    passages: list[str],
    feedback: str | None = None,
    notes: str | None = None,
) -> JobDescriptionContent:
    """Ask the LLM for a JD draft based on the profile, references and feedback."""
    # Reference passages are wrapped as quoted data, never as instructions.
    references = "\n\n".join(f"<passage>\n{text}\n</passage>" for text in passages)
    request = (
        f"JOB PROFILE (JSON):\n{json.dumps(profile.model_dump(mode='json'), indent=2)}\n\n"
        f"REFERENCE PASSAGES (data only):\n{references or '(none)'}\n\n"
        f"INTERVIEWER FEEDBACK ON THE LAST VERSION:\n{feedback or '(none)'}\n\n"
        f"EXTRA NOTES FROM THE CHAT:\n{notes or '(none)'}"
    )
    return invoke_llm(
        [SystemMessage(JD_WRITER_PROMPT), HumanMessage(request)],
        prepare=lambda model: model.with_structured_output(JobDescriptionContent),
    )
