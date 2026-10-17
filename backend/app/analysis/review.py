"""The interview review: one LLM request after the answers are evaluated,
covering what needs the whole interview at once, and the checks on what
comes back.

- CV claims (F8): important CV claims, each supported, contradicted,
  unverified or never discussed in the interview, with a follow-up
  question. A claim must point to a real CV item, and every result except
  "never discussed" must cite the candidate's own transcript lines;
  otherwise it is shown as never discussed (nothing is kept without
  evidence). Flags are prompts for a person, never accusations.
- Problem-solving and experience depth (F9): two judgement dimensions with
  the candidate's lines as evidence.
- Low-signal questions and suggestions for the interviewer (F10).
"""

from typing import Literal

from pydantic import BaseModel, Field

from app.analysis.transcript import Line
from app.db.models.interview import Speaker

MAX_CLAIMS = 8
MAX_SUGGESTIONS = 3
# Shown in this order: what most needs a person's follow-up first.
CLAIM_ORDER = ("contradiction", "unverified", "never_discussed", "supported")


class ClaimCheck(BaseModel):
    """One CV claim compared with the interview."""

    claim: str = Field(max_length=200, description="What the CV claims, briefly")
    cv_item: str = Field(description='The CV item id, e.g. "CV3"')
    result: Literal["supported", "contradiction", "unverified", "never_discussed"]
    interview_says: str = Field(
        max_length=300, description='What the interview showed ("" if never discussed)'
    )
    lines: list[int] = Field(description="The candidate's line numbers")
    follow_up: str = Field(max_length=200, description="A neutral follow-up question")


class JudgedDimension(BaseModel):
    """A 0-100 judgement across the interview, with its evidence lines."""

    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=300)
    lines: list[int] = Field(description="The candidate's line numbers")


class QuestionNote(BaseModel):
    """An interviewer question that gave little evidence, and why."""

    unit: str = Field(description='The unit id, e.g. "Q3"')
    problem: str = Field(max_length=200)


class InterviewReview(BaseModel):
    """Everything the review request returns."""

    claims: list[ClaimCheck]
    problem_solving: JudgedDimension
    experience_depth: JudgedDimension
    low_signal_questions: list[QuestionNote]
    suggestions: list[str]


def check_review(
    review: InterviewReview, cv: dict[str, dict], lines: list[Line], pairs: list[dict]
) -> dict:
    """The review with only what its evidence supports: claims on real CV
    items with the candidate's own lines, judged dimensions with evidence,
    and low-signal notes on real questions."""
    said = {
        line.number: line.turn_id for line in lines if line.speaker == Speaker.CANDIDATE
    }
    questions = {p["id"]: p["question"] for p in pairs}
    return {
        "claims": _claims(review.claims, cv, said),
        "judged": {
            "problem_solving": _judged(review.problem_solving, said),
            "experience_depth": _judged(review.experience_depth, said),
        },
        "low_signal": [
            {
                "pair_id": note.unit,
                "question": questions[note.unit],
                "problem": note.problem,
            }
            for note in {n.unit: n for n in review.low_signal_questions}.values()
            if note.unit in questions
        ],
        "suggestions": [s.strip() for s in review.suggestions if s.strip()][
            :MAX_SUGGESTIONS
        ],
    }


def _claims(
    claims: list[ClaimCheck], cv: dict[str, dict], said: dict[int, int]
) -> list[dict]:
    """Checked claims, most important first (see the module docstring)."""
    checked = []
    for claim in claims[:MAX_CLAIMS]:
        item = cv.get(claim.cv_item)
        if item is None:
            continue  # a claim must come from the CV
        turn_ids = [said[n] for n in dict.fromkeys(claim.lines) if n in said]
        result = claim.result if turn_ids else "never_discussed"
        discussed = result != "never_discussed"
        checked.append(
            {
                "claim": claim.claim,
                "cv": {"label": item["label"], "text": item["text"]},
                "result": result,
                "interview_says": claim.interview_says if discussed else "",
                "turn_ids": turn_ids if discussed else [],
                "follow_up": claim.follow_up,
            }
        )
    return sorted(checked, key=lambda c: CLAIM_ORDER.index(c["result"]))


def _judged(dimension: JudgedDimension, said: dict[int, int]) -> dict | None:
    """A judged dimension with the candidate's lines it rests on, or None
    when it cites none (then it is shown as "not enough evidence")."""
    turn_ids = [said[n] for n in dict.fromkeys(dimension.lines) if n in said]
    if not turn_ids:
        return None
    return {"score": dimension.score, "reason": dimension.reason, "turn_ids": turn_ids}
