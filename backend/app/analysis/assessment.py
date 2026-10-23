"""Building blocks of the consolidated assessment (F6), all plain code so the
numbers are repeatable and every conclusion stays traceable:

- evidence(): what a conclusion may cite. CV items ("CV1", "CV · Work
  history"), requirement coverage records ("R2", for what was never
  explored) and transcript lines ("T12", "Transcript 02:47"), cleaned of
  names and contact details like everything sent to the LLM (N18).
- component_scores() and suitability(): the CV screening score (F2) and the
  four interview dimensions (F5) side by side, and the overall position on
  a 4-step scale. The position is a summary for the interviewer, never a
  decision (B-goals: humans decide).
- check_sources(): keeps only cited ids that exist, so a conclusion either
  rests on real evidence or is shown as unsupported.
"""

from statistics import mean

from sqlalchemy.orm import Session

from app.analysis.qa_pairs import DIMENSIONS
from app.analysis.transcript import Line, clock_text
from app.db.models import Candidate, InterviewSession
from app.interviews.cv_view import clean_text, name_parts

CATEGORIES = ("strengths", "weaknesses", "gaps", "verify")
MAX_CV_ITEM_CHARS = 300
MAX_JOBS = 8
# Overall position: the first step whose minimum the combined score reaches.
POSITIONS = (
    (80, "strong_fit", "Strong fit"),
    (65, "good_fit", "Good fit"),
    (50, "partial_fit", "Partial fit"),
    (0, "not_yet_suitable", "Not yet suitable"),
)
CV_SECTIONS = {
    "experience": "Work history",
    "skills": "Skills",
    "education": "Education",
    "certifications": "Certificates",
    "summary": "Summary",
}


def evidence(
    db: Session,
    session: InterviewSession,
    lines: list[Line],
    matches: list[dict],
    requirements: list[dict],
) -> dict[str, dict]:
    """Everything a conclusion may cite, by id: CV items (the parsed CV and
    the CV lines screening matched to each requirement), each job
    requirement's coverage record (what screening found, which Q&A units
    explored it: the evidence for "never discussed"), then the transcript
    lines."""
    candidate = db.get(Candidate, session.candidate_id)
    names = name_parts(candidate.full_name)
    parsed = candidate.parsed_cv or {}
    items: list[tuple[str, str]] = [
        (
            "Work history",
            f"{j.get('title') or 'Role'} ({j.get('start')} to {j.get('end')})",
        )
        for j in parsed.get("jobs", [])[:MAX_JOBS]
    ]
    if parsed.get("sections", {}).get("skills"):
        items.append(("Skills", parsed["sections"]["skills"]))
    if parsed.get("degree"):
        items.append(("Education", f"Highest degree: {parsed['degree']}"))
    items += [("Certificates", c) for c in parsed.get("certifications", [])]
    items += [
        (CV_SECTIONS.get(m.get("section"), "CV"), m["evidence"])
        for m in matches
        if m.get("evidence")
    ]
    found: dict[str, dict] = {}
    seen = set()
    for section, text in items:
        text = clean_text(text, names)[:MAX_CV_ITEM_CHARS]
        if text and (section, text) not in seen:
            seen.add((section, text))
            found[f"CV{len(found) + 1}"] = {
                "kind": "cv",
                "label": f"CV · {section}",
                "text": text,
            }
    for number, r in enumerate(requirements, start=1):
        interview = ", ".join(r["pair_ids"]) or "never explored"
        found[f"R{number}"] = {
            "kind": "requirement",
            "label": f"Requirement · {r['requirement']}",
            "text": (
                f"{r['requirement']} ({r['level']}). CV screening: "
                f"{r['cv'] or 'not checked'}. Interview: {interview}."
            ),
        }
    for line in lines:
        found[f"T{line.number}"] = {
            "kind": "transcript",
            "label": f"Transcript {clock_text(line.start_ms)}",
            "turn_id": line.turn_id,
            "start_ms": line.start_ms,
            "speaker": line.speaker.value,
            "text": line.text,
        }
    return found


def component_scores(
    screening: dict | None, pairs: list[dict], coverage: list[dict]
) -> dict:
    """The parts the position rests on: CV screening (F2), the interview's
    four dimensions averaged over the scored Q&A units (F5), and how many
    job requirements the interview explored."""
    cv = None
    if screening and screening.get("overall") is not None:
        cv = {
            "overall": round(screening["overall"]),
            "rank": screening.get("rank"),
            "ranked_count": screening.get("ranked_count"),
            "dimensions": {
                key: {
                    "label": d["label"],
                    "score": d["score"],
                    "reason": d.get("reason"),
                }
                for key, d in screening.get("dimensions", {}).items()
            },
        }
    scored = [p for p in pairs if p.get("status") == "scored"]
    interview = None
    if scored:
        interview = {
            name: round(mean(p["scores"][name]["score"] for p in scored))
            for name in DIMENSIONS
        }
        interview |= {"overall": round(mean(interview.values())), "scored": len(scored)}
    return {
        "cv": cv,
        "interview": interview,
        "coverage": {
            "explored": sum(bool(c["pair_ids"]) for c in coverage),
            "total": len(coverage),
            "unexplored": [c["requirement"] for c in coverage if not c["pair_ids"]],
        },
    }


def suitability(components: dict) -> dict:
    """The overall position: the average of the CV and interview scores that
    exist, on a 4-step scale. Without either, there is not enough evidence."""
    parts = [
        part["overall"]
        for part in (components["cv"], components["interview"])
        if part is not None
    ]
    if not parts:
        return {
            "key": "not_enough_evidence",
            "label": "Not enough evidence",
            "score": None,
        }
    score = round(mean(parts))
    _minimum, key, label = next(p for p in POSITIONS if score >= p[0])
    return {"key": key, "label": label, "score": score}


def check_sources(findings: list[dict], known: dict[str, dict]) -> list[dict]:
    """The findings with only the cited ids that exist (in order, once)."""
    return [
        finding
        | {
            "sources": [
                s for s in dict.fromkeys(finding.get("sources", [])) if s in known
            ]
        }
        for finding in findings
    ]
