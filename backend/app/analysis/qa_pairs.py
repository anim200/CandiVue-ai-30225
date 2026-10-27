"""Question–answer units of an interview and how they cover the job (F5).

The LLM proposes the units (segmentation) and evaluates them in batches;
this module checks every answer against the transcript before anything is
kept:
line numbers must exist and come from the right person, a multi-part
question becomes Q6a / Q6b, a follow-up is linked to the question it follows,
and the requirements a unit explores must be the job's own. Coverage and the
requirements never explored are worked out here, not by the LLM, so they are
exact.
"""

from string import ascii_lowercase
from typing import Literal

from pydantic import BaseModel, Field

from app.analysis.transcript import Line
from app.db.models.interview import Speaker

DIMENSIONS = ("relevance", "accuracy", "completeness", "articulation")
# At most this many units are kept. Not a schema limit: Gemini refuses a
# response schema with a large maxItems on a list of objects (too complex).
MAX_UNITS = 60
NOT_SCORED = {
    "other": "Small talk, logistics or not about the job: not scored.",
    "unanswered": "No answer from the candidate in the transcript.",
    "missing": "No evaluation came back for this answer: use Analyse again.",
}


class QAUnit(BaseModel):
    """One question from the interviewer and the candidate's answer to it."""

    question: str = Field(
        max_length=500, description="The question as asked (shortened if long)"
    )
    question_lines: list[int] = Field(description="Line numbers of the question")
    answer_lines: list[int] = Field(description="Line numbers of the answer")
    kind: Literal["job", "company", "other"]
    follows_up: int | None = Field(
        default=None,
        description="Number of the earlier unit this one follows up, or null",
    )


class Segmentation(BaseModel):
    """The units the LLM found, in the order they were asked."""

    units: list[QAUnit]


class DimensionScore(BaseModel):
    """One quality dimension of an answer: 0-100 and why."""

    score: int = Field(ge=0, le=100)
    reason: str = Field(max_length=300)


class Evaluation(BaseModel):
    """The LLM's evaluation of one answer."""

    unit: str = Field(description='The unit id, e.g. "Q2a"')
    relevance: DimensionScore
    accuracy: DimensionScore
    completeness: DimensionScore
    articulation: DimensionScore
    summary: str = Field(max_length=400, description="Why these scores, briefly")
    evidence_lines: list[int] = Field(
        description="Line numbers that best support the evaluation"
    )
    requirements: list[int] = Field(
        description="Numbers of the job requirements this answer explores"
    )
    sources: list[int] = Field(
        description="Numbers of the unit's reference passages used to judge accuracy"
    )


class Evaluations(BaseModel):
    """The evaluations of one batch of answers (one per unit)."""

    evaluations: list[Evaluation]


def build_pairs(units: list[QAUnit], lines: list[Line]) -> list[dict]:
    """Check the LLM's units against the transcript and number them.

    Kept: question lines spoken by the interviewer, answer lines spoken by
    the candidate (others are dropped; a unit without a question is
    dropped). Units are ordered by when they were asked. Units sharing the
    same question lines are the parts of one multi-part question (Q6a, Q6b).
    """
    by_number = {line.number: line for line in lines}

    def spoken_by(numbers: list[int], speaker: Speaker) -> tuple[int, ...]:
        """The given line numbers that exist and were spoken by `speaker`."""
        return tuple(
            sorted(
                {
                    n
                    for n in numbers
                    if n in by_number and by_number[n].speaker == speaker
                }
            )
        )

    checked, seen = [], set()
    for index, unit in enumerate(units[:MAX_UNITS], start=1):
        question = " ".join(unit.question.split())
        asked = spoken_by(unit.question_lines, Speaker.INTERVIEWER)
        answered = spoken_by(unit.answer_lines, Speaker.CANDIDATE)
        key = (question.lower(), asked, answered)
        if not question or not asked or key in seen:
            continue
        seen.add(key)
        checked.append((index, unit, question, asked, answered))
    checked.sort(key=lambda item: item[3][0])  # stable: parts keep their order

    pairs, ids = [], {}
    number, position = 0, 0
    while position < len(checked):
        group_end = position + 1
        while (
            group_end < len(checked) and checked[group_end][3] == checked[position][3]
        ):
            group_end += 1
        group = checked[position:group_end][: len(ascii_lowercase)]
        number += 1
        for part, (index, unit, question, asked, answered) in enumerate(group, start=1):
            multi = len(group) > 1
            pair_id = f"Q{number}{ascii_lowercase[part - 1]}" if multi else f"Q{number}"
            ids[index] = pair_id
            pairs.append(
                _pair(pair_id, question, unit, asked, answered, by_number)
                | {"part": [part, len(group)] if multi else None}
            )
        position = group_end
    checked = [item for item in checked if item[0] in ids]

    for (index, unit, *_rest), pair in zip(checked, pairs, strict=True):
        earlier = ids.get(unit.follows_up) if unit.follows_up else None
        if earlier and earlier != ids[index] and _before(earlier, pairs, pair):
            pair["follow_up_of"] = earlier
    return pairs


def apply_evaluation(
    pair: dict, evaluation: Evaluation, requirements: list[dict], passages: list[dict]
) -> dict:
    """The pair with its checked evaluation: scores, why, the lines and
    reference passages it rests on, and the job requirements it explores."""
    by_number = dict(zip(pair["lines"], pair["turn_ids"], strict=True))
    evidence = [
        by_number[n] for n in dict.fromkeys(evaluation.evidence_lines) if n in by_number
    ]
    explored = [
        requirements[n - 1]["text"]
        for n in dict.fromkeys(evaluation.requirements)
        if 1 <= n <= len(requirements)
    ]
    used = [
        passages[n - 1]
        for n in dict.fromkeys(evaluation.sources)
        if 1 <= n <= len(passages)
    ]
    return pair | {
        "status": "scored",
        "scores": {name: getattr(evaluation, name).model_dump() for name in DIMENSIONS},
        "summary": evaluation.summary,
        "evidence_turn_ids": evidence or pair["answer_turn_ids"],
        "requirements": explored,
        "sources": used,
        # Accuracy was checked against a reference document, not only the
        # model's own knowledge.
        "verified": bool(used),
    }


def is_scored(pair: dict) -> bool:
    """Only answered job- or company-related questions are evaluated (F5:
    greetings and small talk stay in the transcript but are not scored)."""
    return pair["kind"] != "other" and pair["answered"]


def not_scored(pair: dict, reason: str | None = None) -> dict:
    """The pair marked as not scored, with the reason shown on screen
    (by default: small talk, or no answer)."""
    reason = reason or ("other" if pair["kind"] == "other" else "unanswered")
    return pair | {"status": "not_scored", "reason": NOT_SCORED[reason]}


def coverage(requirements: list[dict], pairs: list[dict]) -> list[dict]:
    """Each job requirement with the Q&A units that explored it (empty:
    never explored in the interview)."""
    return [
        {
            "requirement": requirement["text"],
            "level": requirement.get("level"),
            "pair_ids": [
                p["id"]
                for p in pairs
                if requirement["text"] in p.get("requirements", [])
            ],
        }
        for requirement in requirements
    ]


def _pair(pair_id, question, unit, asked, answered, by_number) -> dict:
    """One pair as it is saved (scores are added after evaluation)."""
    lines = [*asked, *answered]
    return {
        "id": pair_id,
        "question": question,
        "kind": unit.kind,
        "answered": bool(answered),
        "lines": lines,
        "turn_ids": [by_number[n].turn_id for n in lines],
        "question_turn_ids": [by_number[n].turn_id for n in asked],
        "answer_turn_ids": [by_number[n].turn_id for n in answered],
        "start_ms": min(by_number[n].start_ms for n in lines),
        "end_ms": max(by_number[n].end_ms for n in lines),
        "follow_up_of": None,
    }


def _before(earlier_id: str, pairs: list[dict], pair: dict) -> bool:
    """True when `earlier_id` comes before `pair` (a follow-up looks back)."""
    order = [p["id"] for p in pairs]
    return order.index(earlier_id) < order.index(pair["id"])
