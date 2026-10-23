"""The candidate's CV as the interview room uses it.

- overview(): everything the interviewer's CV panel shows (facts parsed
  from the CV and the candidate's latest screening result). Interviewers
  only (N9).
- ai_summary(): a reduced version for the Hiring Assistant's questions,
  sent to the LLM provider (Gemini). It has no name, email, phone, address
  or links: only job titles with their dates, skills, degree level,
  certificates and how each job requirement was met (README, N18).
"""

import re

from sqlalchemy.orm import Session

from app.collector.intake import find_cv
from app.db.models import Candidate, InterviewSession, Job
from app.interviews import ranking

MAX_SKILLS_CHARS = 600
MAX_EVIDENCE_CHARS = 160
MAX_JOBS = 8
# Contact details and links are removed from every text sent to the LLM.
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
PHONE = re.compile(r"\+?\d[\d\s()-]{7,}\d")
LINK = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)


def screening_result(db: Session, job: Job, candidate_id: int) -> dict | None:
    """The candidate's result in the job's latest finished screening, or None."""
    try:
        _run, rows = ranking.latest_rows(db, job)
    except ValueError:
        return None
    row = next((r for r in rows if r.candidate.id == candidate_id), None)
    if row is None:
        return None
    return {
        "passed": row.ranked,
        "overall": row.score.overall_score,
        "rank": row.score.rank,
        "ranked_count": sum(r.ranked for r in rows),
        "dimensions": row.score.dimension_scores or {},
        "matches": row.score.requirement_matches or [],
        "summary": row.score.summary,
    }


def overview(db: Session, session: InterviewSession) -> dict:
    """The interviewer's CV panel: contact, parsed facts, screening result."""
    candidate = db.get(Candidate, session.candidate_id)
    job = db.get(Job, session.job_id)
    parsed = candidate.parsed_cv or {}
    path = find_cv(job.id, candidate.id)
    years_known = parsed.get("years_source") not in (None, "unknown")
    return {
        "candidate_id": candidate.id,
        "job_id": job.id,
        "name": candidate.full_name or candidate.cv_filename,
        "email": candidate.email,
        "cv_filename": candidate.cv_filename,
        "file_type": path.suffix.lstrip(".") if path else None,
        "parsed": bool(parsed),
        "years": parsed.get("years_experience") if years_known else None,
        "degree": parsed.get("degree"),
        "certifications": parsed.get("certifications", []),
        "jobs": [
            {"title": j.get("title"), "start": j.get("start"), "end": j.get("end")}
            for j in parsed.get("jobs", [])[:MAX_JOBS]
        ],
        "skills": (parsed.get("sections", {}).get("skills") or "")[:MAX_SKILLS_CHARS]
        or None,
        "screening": screening_result(db, job, candidate.id),
    }


def ai_summary(db: Session, session: InterviewSession) -> str | None:
    """The reduced CV summary for the LLM (see the module docstring), or
    None when the CV has not been read yet (not screened)."""
    candidate = db.get(Candidate, session.candidate_id)
    job = db.get(Job, session.job_id)
    parsed = candidate.parsed_cv
    if not parsed:
        return None
    names = name_parts(candidate.full_name)
    lines = [f"Job: {job.title}"]
    if parsed.get("years_source") not in (None, "unknown"):
        lines.append(f"Years of experience: about {parsed['years_experience']:g}")
    if parsed.get("degree"):
        lines.append(f"Highest degree: {parsed['degree']}")
    jobs = [
        f"- {clean_text(j.get('title') or 'Untitled role', names)} ({j.get('start')} to {j.get('end')})"
        for j in parsed.get("jobs", [])[:MAX_JOBS]
    ]
    if jobs:
        lines += ["Roles:", *jobs]
    skills = parsed.get("sections", {}).get("skills")
    if skills:
        lines.append(f"Skills: {clean_text(skills[:MAX_SKILLS_CHARS], names)}")
    certificates = [clean_text(c, names) for c in parsed.get("certifications", [])]
    if certificates:
        lines.append("Certificates: " + "; ".join(certificates))
    result = screening_result(db, job, candidate.id)
    if result and result["matches"]:
        lines.append("Job requirements and what the CV shows:")
        for match in result["matches"]:
            evidence = match.get("evidence")
            shown = (
                f': "{clean_text(evidence[:MAX_EVIDENCE_CHARS], names)}"'
                if evidence
                else ""
            )
            lines.append(
                f"- {match['requirement']} ({match['level']}): "
                f"{match['status'].replace('partial', 'partly met')}{shown}"
            )
    return "\n".join(lines)


def name_parts(*full_names: str | None) -> list[str]:
    """The words of people's names, to remove them from texts for the LLM
    (single letters are left alone: they also occur in normal text)."""
    return [
        part for name in full_names for part in (name or "").split() if len(part) > 1
    ]


def clean_text(text: str, names: list[str]) -> str:
    """Remove contact details, links and the candidate's name from a text."""
    text = LINK.sub("[link]", EMAIL.sub("[email]", text))
    # A phone number has 9+ digits; "2014 - 2018" (8 digits) is a date range.
    text = PHONE.sub(
        lambda m: "[phone]" if sum(c.isdigit() for c in m[0]) >= 9 else m[0], text
    )
    for name in names:
        text = re.sub(rf"\b{re.escape(name)}\b", "[name]", text, flags=re.IGNORECASE)
    return " ".join(text.split())
