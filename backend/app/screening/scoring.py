"""Hard-requirement gate and the 0-100 scores (F1 gate, F2 scoring).

All rules, no AI: the same CV and job give the same scores (F2, B2). Each
dimension gets a short written reason built from the evidence.

Gate (trainer clarification: failing a mandatory requirement = excluded):
- a mandatory requirement passes when it is met, or partly met through a
  named close substitute ("related", e.g. Podman for Docker);
- "partly met" only by meaning is too weak for a must-have: excluded;
- fewer years than the profile's minimum: excluded. Years that could not be
  read never exclude anyone: the candidate is ranked with a warning.

Dimensions, each 0-100:
- skills: skill requirements, weighted mandatory 3 / required 2 / preferred 1;
  met counts fully, partly met half;
- experience: years against the minimum (minimum + 3 years = full marks);
- qualifications: highest degree (60%) and qualification requirements (40%);
- ats: how many of the job's key terms the CV contains (60%) and how close
  the whole CV is to the job description in meaning (40%).
"""

from app.screening.weights import DIMENSION_LABELS, DIMENSIONS

LEVEL_WEIGHT = {"mandatory": 3, "required": 2, "preferred": 1}
STATUS_CREDIT = {"met": 1.0, "partial": 0.5, "unmet": 0.0}
DEGREE_SCORE = {"doctorate": 100, "master": 95, "bachelor": 85, "diploma": 60, None: 30}
EXTRA_YEARS_FOR_FULL_MARKS = 3
# Similarity of the whole CV to the JD, mapped to 0-100 (calibrated on the
# synthetic CVs: unrelated CVs ≈ 0.35, close ones ≈ 0.75).
ATS_SIMILARITY_RANGE = (0.35, 0.75)


def check_gate(
    matches: list[dict],
    years: float | None,
    min_years: int | None,
    years_source: str = "dates",
) -> list[str]:
    """Reasons the candidate fails the hard requirements (empty = passes).
    `years` is None when the CV's years could not be read."""
    reasons = []
    for match in matches:
        if not fails_mandatory(match):
            continue
        if match["status"] == "unmet":
            reasons.append(
                f"Mandatory requirement not shown in the CV: {match['requirement']}."
            )
        else:
            reasons.append(
                f"Only loosely related evidence for a mandatory requirement: "
                f"{match['requirement']}."
            )
    if too_few_years(years, min_years):
        how = (
            " (read by the local model; no job dates found)"
            if years_source == "model"
            else ""
        )
        reasons.append(
            f"About {years:g} years of experience{how}; "
            f"the job needs at least {min_years}."
        )
    return reasons


def fails_mandatory(match: dict) -> bool:
    """A mandatory requirement not met, or only partly met by meaning."""
    return match["level"] == "mandatory" and (
        match["status"] == "unmet"
        or (match["status"] == "partial" and match["decided_by"] == "meaning")
    )


def too_few_years(years: float | None, min_years: int | None) -> bool:
    """Fewer years than the minimum (unknown years never count as too few)."""
    return bool(min_years) and years is not None and years < min_years


def score_skills(matches: list[dict]) -> tuple[int, str]:
    """Skill requirements met, weighted by level."""
    skills = [m for m in matches if m["category"] in ("skill", "other")]
    if not skills:
        return 100, "The job lists no skill requirements."
    total = sum(LEVEL_WEIGHT[m["level"]] for m in skills)
    earned = sum(LEVEL_WEIGHT[m["level"]] * STATUS_CREDIT[m["status"]] for m in skills)
    met = [m["requirement"] for m in skills if m["status"] == "met"]
    partial = [m["requirement"] for m in skills if m["status"] == "partial"]
    missing = [m["requirement"] for m in skills if m["status"] == "unmet"]
    reason = f"{len(met)} of {len(skills)} skills met"
    if met:
        reason += f" ({', '.join(met)})"
    if partial:
        reason += f"; partly: {', '.join(partial)}"
    if missing:
        reason += f"; missing: {', '.join(missing)}"
    return round(100 * earned / total), reason + "."


def score_experience(
    years: float | None,
    min_years: int | None,
    jobs: list[dict],
    years_source: str = "dates",
    evidence: list[str] | None = None,
) -> tuple[int, str]:
    """Years of experience against the minimum. years_source: "dates" (job
    dates), "model" (read from the CV by the local model) or "unknown"."""
    needed = f"; the job needs {min_years}+" if min_years else ""
    if years is None:
        return 0, (
            "Years of experience could not be read from the CV (no job dates or "
            f"stated years found): please check the CV{needed}."
        )
    target = (min_years or 0) + EXTRA_YEARS_FOR_FULL_MARKS
    score = round(100 * min(1.0, years / target)) if target else 100
    if years_source == "model":
        quote = f": “{evidence[0]}”" if evidence else ""
        return score, (
            f"About {years:g} years, read from the CV by the local model{quote} "
            f"(no job dates found){needed}."
        )
    roles = len(jobs)
    return (
        score,
        f"About {years:g} years across {roles} role{'s' if roles != 1 else ''}{needed}.",
    )


def score_qualifications(degree: str | None, matches: list[dict]) -> tuple[int, str]:
    """Highest degree, plus any qualification requirements (certificates)."""
    degree_score = DEGREE_SCORE.get(degree, 30)
    wanted = [m for m in matches if m["category"] == "qualification"]
    degree_text = f"Highest degree: {degree}" if degree else "No degree found"
    if not wanted:
        return degree_score, degree_text + "."
    share = sum(STATUS_CREDIT[m["status"]] for m in wanted) / len(wanted)
    parts = [
        f"{m['requirement']}: {m['status'].replace('partial', 'partly met')}"
        for m in wanted
    ]
    return round(0.6 * degree_score + 40 * share), f"{degree_text}; {'; '.join(parts)}."


def score_ats(cv_text: str, key_terms: list[str], similarity: float) -> tuple[int, str]:
    """Key-term coverage and overall closeness of the CV to the JD."""
    text = cv_text.lower()
    found = [term for term in key_terms if term.lower() in text]
    coverage = len(found) / len(key_terms) if key_terms else 0.0
    low, high = ATS_SIMILARITY_RANGE
    closeness = min(1.0, max(0.0, (similarity - low) / (high - low)))
    score = round(100 * (0.6 * coverage + 0.4 * closeness))
    return score, (
        f"{len(found)} of {len(key_terms)} key job terms appear in the CV; "
        f"overall closeness to the job description {round(100 * closeness)}%."
    )


def combine(dimension_scores: dict[str, int], weights: dict) -> int:
    """Weighted overall score 0-100."""
    return round(sum(dimension_scores[d] * weights[d] for d in DIMENSIONS) / 100)


def dimension_rows(scores: dict, reasons: dict, weights: dict) -> dict:
    """The per-dimension breakdown saved with each result and shown on screen."""
    return {
        dimension: {
            "label": DIMENSION_LABELS[dimension],
            "score": scores[dimension],
            "weight": weights[dimension],
            "reason": reasons[dimension],
        }
        for dimension in DIMENSIONS
    }
