"""Interview score (F9): how the candidate did in the interview, on six
dimensions with evidence, kept separate from the CV score (F2).

Four dimensions are worked out here from the Q&A evaluations (F5), so they
cost no AI request and are repeatable; two need judgement across the whole
interview and come from the interview review (one request, app/analysis/
review.py). Every dimension says what it rests on: Q&A units (Q2a) or the
candidate's transcript lines.
"""

from statistics import mean

LABELS = {
    "technical": "Technical competency",
    "communication": "Communication",
    "relevance": "Response relevance",
    "problem_solving": "Problem-solving approach",
    "experience_depth": "Experience depth",
    "job_alignment": "Job alignment",
}


def interview_score(
    pairs: list[dict], coverage: list[dict], judged: dict
) -> dict | None:
    """The six dimensions and their average (the overall interview score),
    or None when no answer was scored. judged: the review's
    problem_solving and experience_depth (None when it found no evidence).
    A dimension without evidence is shown as such and left out of the
    average."""
    scored = [p for p in pairs if p.get("status") == "scored"]
    if not scored:
        return None
    job_answers = [p for p in scored if p["kind"] == "job"] or scored
    dimensions = {
        "technical": _average(job_answers, "accuracy", "accuracy of the job answers"),
        "communication": _average(scored, "articulation", "articulation"),
        "relevance": _average(scored, "relevance", "relevance"),
        "problem_solving": judged.get("problem_solving"),
        "experience_depth": judged.get("experience_depth"),
        "job_alignment": _alignment(scored, coverage),
    }
    shown = {
        key: (
            value or {"score": None, "reason": "Not enough evidence in the interview."}
        )
        | {"label": LABELS[key]}
        for key, value in dimensions.items()
    }
    known = [d["score"] for d in shown.values() if d["score"] is not None]
    return {"overall": round(mean(known)), "scored": len(scored), "dimensions": shown}


def _average(pairs: list[dict], name: str, what: str) -> dict:
    """One F5 dimension averaged over the given answers."""
    ids = [p["id"] for p in pairs]
    return {
        "score": round(mean(p["scores"][name]["score"] for p in pairs)),
        "reason": f"Average {what} over {len(ids)} answers ({', '.join(ids)}).",
        "pair_ids": ids,
    }


def _alignment(scored: list[dict], coverage: list[dict]) -> dict | None:
    """How well the answers showed the job requirements they explored: for
    each explored requirement its best answer (accuracy and completeness),
    averaged. None when the interview explored no requirement."""
    by_id = {p["id"]: p for p in scored}
    best = {}
    for row in coverage:
        answers = [by_id[i] for i in row["pair_ids"] if i in by_id]
        if answers:
            best[row["requirement"]] = max(
                (
                    a["scores"]["accuracy"]["score"]
                    + a["scores"]["completeness"]["score"]
                )
                / 2
                for a in answers
            )
    if not best:
        return None
    listed = ", ".join(f"{name} {round(value)}" for name, value in best.items())
    return {
        "score": round(mean(best.values())),
        "reason": f"Best answer per explored requirement ({len(best)} of {len(coverage)}): {listed}.",
        "pair_ids": list(
            dict.fromkeys(i for row in coverage for i in row["pair_ids"] if i in by_id)
        ),
    }
