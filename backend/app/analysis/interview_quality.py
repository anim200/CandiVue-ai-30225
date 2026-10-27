"""Interview quality (F10): how good the interview was as evidence, not how
good the candidate was.

Measured here in plain code (no AI request, repeatable): who did the
talking, how many job questions were answered, which required skills were
explored. The interview review adds the questions that gave little evidence
and a few suggestions. The verdict follows fixed rules; a poor interview is
not treated as enough evidence: the page offers to invite the candidate
again (trainer clarification). consistency() compares the interview with
the job's other analysed interviews when the page is opened, so it always
uses the latest ones.
"""

from statistics import median

from app.analysis.transcript import Line
from app.db.models.interview import Speaker

MIN_JOB_QUESTIONS = 3  # fewer answered job questions: too little evidence
POOR_TALK_SHARE = 75  # the interviewer talked more than this % of the time
HIGH_TALK_SHARE = 60
POOR_COVERAGE = 0.5  # less than half of the mandatory requirements explored


def interview_quality(
    pairs: list[dict], coverage: list[dict], lines: list[Line], review: dict | None
) -> dict:
    """The verdict (good / needs_attention / poor) with its reasons, the
    measurements behind it and suggestions for the next interview."""
    talk = _talk_share(lines)
    answered = sum(p.get("status") == "scored" for p in pairs)
    mandatory = [c for c in coverage if c.get("level") == "mandatory"]
    unexplored = [c["requirement"] for c in mandatory if not c["pair_ids"]]
    explored_share = 1 - len(unexplored) / len(mandatory) if mandatory else 1
    low_signal = (review or {}).get("low_signal", [])

    poor, attention = [], []
    if not lines:
        poor.append("There is no transcript of this interview.")
    elif answered < MIN_JOB_QUESTIONS:
        poor.append(f"Only {answered} job-related questions were answered.")
    if explored_share < POOR_COVERAGE:
        poor.append(
            f"Only {len(mandatory) - len(unexplored)} of {len(mandatory)} mandatory requirements were explored."
        )
    elif unexplored:
        attention.append(f"Not explored: {', '.join(unexplored)}.")
    if talk and talk["interviewer"] > POOR_TALK_SHARE:
        poor.append(f"The interviewer did {talk['interviewer']}% of the talking.")
    elif talk and talk["interviewer"] > HIGH_TALK_SHARE:
        attention.append(f"The interviewer did {talk['interviewer']}% of the talking.")
    if len(low_signal) >= 2:
        attention.append(f"{len(low_signal)} questions gave little evidence.")

    suggestions = [f"Ask about {name} next time." for name in unexplored]
    if talk and talk["interviewer"] > HIGH_TALK_SHARE:
        suggestions.append(
            "Ask shorter, open questions and let the candidate talk more."
        )
    suggestions += (review or {}).get("suggestions", [])
    verdict = "poor" if poor else "needs_attention" if attention else "good"
    return {
        "verdict": verdict,
        "reasons": poor + attention,
        "talk": talk,
        "answered": answered,
        "mandatory": {
            "explored": len(mandatory) - len(unexplored),
            "total": len(mandatory),
        },
        "low_signal": low_signal,
        "suggestions": suggestions,
    }


def consistency(results: dict, others: list[dict]) -> dict | None:
    """This interview next to the job's other analysed interviews with
    answers (empty ones say nothing about how interviews usually go):
    answered job questions and explored requirements (this one vs the
    typical one), and requirements most of them explored but this one did
    not. None when there is nothing to compare with."""
    others = [other for other in others if other.get("scored")]
    if not others:
        return None

    def explored(r: dict) -> set[str]:
        """The requirements an interview explored."""
        return {c["requirement"] for c in r.get("coverage", []) if c["pair_ids"]}

    counts: dict[str, int] = {}
    for other in others:
        for name in explored(other):
            counts[name] = counts.get(name, 0) + 1
    usual = {name for name, n in counts.items() if n * 2 >= len(others)}
    return {
        "compared_with": len(others),
        "answered": {
            "this": results.get("scored", 0),
            "typical": round(median(o.get("scored", 0) for o in others)),
        },
        "explored": {
            "this": len(explored(results)),
            "typical": round(median(len(explored(o)) for o in others)),
        },
        "missing_usual": sorted(usual - explored(results)),
    }


def _talk_share(lines: list[Line]) -> dict | None:
    """Each side's share of the speaking time in %, or None without speech."""
    spoken = {Speaker.INTERVIEWER: 0, Speaker.CANDIDATE: 0}
    for line in lines:
        spoken[line.speaker] += max(line.end_ms - line.start_ms, 0)
    total = sum(spoken.values())
    if not total:
        return None
    interviewer = round(100 * spoken[Speaker.INTERVIEWER] / total)
    return {"interviewer": interviewer, "candidate": 100 - interviewer}
