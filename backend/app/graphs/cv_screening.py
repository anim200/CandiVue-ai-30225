r"""LangGraph 2: CV Screening & Scoring (Figure 4). A fixed workflow, started
by the "Screen CVs" button (not by the chatbot), so scores stay repeatable.

    START → load_cv_batch ─ Send: one screen_cv branch per CV, in parallel
    screen_cv:
        extract_text ─ text found ─────────────→ parse_cv
                     ├ no text → ocr_extract ──→ parse_cv
                     └ error ──→ log_and_skip
        parse_cv ─ error → log_and_skip
                 └→ check_hard_requirements ─ fail → record_exclusion
                                            └ pass → match_requirements
        match_requirements → score_skills ║ score_experience ║
                             score_qualifications ║ ats_match → combine_scores
    → collect_results → rank_candidates → save_results → END

- Every node is local work (no Gemini): see app/screening. The local model
  (local_model.py) is asked only in two cases: parse_cv, when the rules
  found no job dates; check_hard_requirements, before excluding a
  candidate for a mandatory requirement the rules did not find.
- One bad CV goes to log_and_skip; the rest of the batch goes on (F1).
- State is checkpointed in PostgreSQL: after a restart the run continues
  where it stopped (N26). Parsed CVs and their embeddings are stored, so a
  later run reuses them.
"""

import json
import logging
import operator
import re
from collections import Counter
from datetime import UTC, datetime
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy import delete, select, update

from app.ai.embeddings import embed_documents, embed_query
from app.ai.errors import AIServiceError
from app.collector.intake import find_cv
from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import (
    Candidate,
    CandidateScore,
    CvPassage,
    Job,
    JobDescription,
    ScreeningRun,
)
from app.db.models.candidate import CandidateStatus
from app.db.models.job import JobDescriptionStatus
from app.graphs.checkpointer import open_checkpointer
from app.runs.runner import graph_config, register_run_kind
from app.screening import local_model, scoring
from app.screening.matching import (
    cv_passages,
    embed_passages,
    match_requirements,
    requirement_vectors,
    too_few_years,
)
from app.screening.parsing import PARSER_VERSION
from app.screening.parsing import parse_cv as parse_cv_text
from app.screening.text import (
    UnreadableCv,
    has_text,
    ocr_text,
)
from app.screening.text import (
    extract_text as read_text_layer,
)

logger = logging.getLogger(__name__)

RUN_KIND = "cv_screening"
MAX_CV_CHARS_FOR_ATS = 3000  # enough of the CV to compare with the JD
KEY_TERM_COUNT = 20
STOPWORDS = frozenset(
    """about across after also and any are because been being both build
    building can clean code company could daily design develop developing
    each ensure etc every experience for from good have help high
    including into join our over part role should skills strong team teams
    that the their them these they this through using well what when where
    which while will with within work working you your years year""".split()  # noqa: SIM905 - easier to read
)


class ScreeningState(TypedDict, total=False):
    """The whole run: the job context and the results of every CV."""

    run_id: int
    job_id: int
    context: dict  # requirements, minimum years, weights, JD terms and vector
    candidate_ids: list[int]
    results: Annotated[list[dict], operator.add]  # one per CV, from the branches
    ranked: list[dict]


class CvState(TypedDict, total=False):
    """One CV's branch (screen_cv subgraph)."""

    run_id: int
    candidate_id: int
    context: dict
    text: str
    used_ocr: bool
    previous: dict  # parsed by older rules: parsed again, embeddings reused
    parsed: dict
    matches: list[dict]
    gate_reasons: list[str]
    error: str
    scores: Annotated[dict, operator.or_]  # each score node adds its dimension
    reasons: Annotated[dict, operator.or_]
    results: Annotated[list[dict], operator.add]


class CvOutput(TypedDict):
    """What one branch hands back to the batch: only its result (parallel
    branches must not all write the shared run fields)."""

    results: Annotated[list[dict], operator.add]


# ---------- the whole batch ----------


def load_cv_batch(state: ScreeningState) -> dict:
    """Read the job (requirements, weights, JD) and the CVs to screen."""
    with SessionLocal() as db:
        run = db.get(ScreeningRun, state["run_id"])
        job = db.get(Job, run.job_id)
        jd = db.scalar(
            select(JobDescription)
            .where(
                JobDescription.job_id == job.id,
                JobDescription.status == JobDescriptionStatus.APPROVED,
            )
            .order_by(JobDescription.version.desc())
            .limit(1)
        )
        candidate_ids = list(
            db.scalars(
                select(Candidate.id)
                .where(
                    Candidate.job_id == job.id,
                    Candidate.status != CandidateStatus.REJECTED,
                )
                .order_by(Candidate.id)
            )
        )
        run.total, run.processed = len(candidate_ids), 0
        db.commit()
        profile = job.profile or {}
        jd_text = jd_plain_text(jd.content) if jd else ""
    requirements = profile.get("requirements", [])
    context = {
        "requirements": requirements,
        "min_years": profile.get("min_years_experience"),
        "weights": run_weights(state["run_id"]),
        "key_terms": key_terms(jd_text, requirements),
        # Made once for the whole batch, not once per CV.
        "requirement_vectors": requirement_vectors(requirements),
        "jd_vector": embed_query(jd_text[:MAX_CV_CHARS_FOR_ATS]) if jd_text else None,
    }
    return {"job_id": job.id, "context": context, "candidate_ids": candidate_ids}


def send_cvs(state: ScreeningState) -> list[Send]:
    """Fan out: one screen_cv branch per CV, run in parallel."""
    return [
        Send(
            "screen_cv",
            {
                "run_id": state["run_id"],
                "candidate_id": cid,
                "context": state["context"],
            },
        )
        for cid in state["candidate_ids"]
    ] or [Send("collect_results", state)]


def collect_results(state: ScreeningState) -> dict:
    """All branches are back: nothing to do but wait for them (fan-in)."""
    return {}


def rank_candidates(state: ScreeningState) -> dict:
    """Order the candidates who passed the gate: best overall score first
    (ties: higher skills score, then the earlier CV)."""
    passed = [r for r in state["results"] if r["outcome"] == "ranked"]
    passed.sort(
        key=lambda r: (-r["overall"], -r["scores"]["skills"], r["candidate_id"])
    )
    for position, result in enumerate(passed, start=1):
        result["rank"] = position
    return {"ranked": passed}


def save_results(state: ScreeningState) -> dict:
    """Save one row per CV for this run (ranked, excluded or unreadable)."""
    ranks = {r["candidate_id"]: r["rank"] for r in state.get("ranked", [])}
    with SessionLocal() as db:
        db.execute(
            delete(CandidateScore).where(
                CandidateScore.screening_run_id == state["run_id"]
            )
        )
        for result in state["results"]:
            db.add(
                CandidateScore(
                    screening_run_id=state["run_id"],
                    candidate_id=result["candidate_id"],
                    passed_gate=result["outcome"] == "ranked",
                    requirement_matches=result.get("matches", []),
                    dimension_scores=result.get("dimensions", {}),
                    overall_score=result.get("overall"),
                    rank=ranks.get(result["candidate_id"]),
                    summary=result["summary"],
                )
            )
        run = db.get(ScreeningRun, state["run_id"])
        run.processed = run.total
        db.commit()
    logger.info(
        "Screening run %d saved: %d CVs", state["run_id"], len(state["results"])
    )
    return {}


# ---------- one CV (screen_cv subgraph) ----------


def extract_text(state: CvState) -> dict:
    """Read the CV's own text, or reuse the text parsed in an earlier run
    (parsed again when the parsing rules changed since)."""
    with SessionLocal() as db:
        candidate = db.get(Candidate, state["candidate_id"])
        parsed = candidate.parsed_cv
        if parsed and candidate.status == CandidateStatus.PARSED:
            if parsed.get("parser_version") == PARSER_VERSION:
                return {"parsed": parsed, "text": parsed["text"]}
            return {
                "text": parsed["text"],
                "used_ocr": parsed.get("used_ocr", False),
                "previous": parsed,
            }
        job_id = candidate.job_id
    path = find_cv(job_id, state["candidate_id"])
    if path is None:
        return {"error": "The CV file is missing."}
    try:
        return {"text": read_text_layer(path), "used_ocr": False}
    except UnreadableCv as exc:
        return {"error": str(exc)}


def after_extract(state: CvState) -> str:
    """Route: error → log_and_skip; no text → ocr_extract; else parse_cv."""
    if state.get("error"):
        return "log_and_skip"
    if state.get("parsed"):
        return "check_hard_requirements"  # parsed before: reuse it
    if state.get("previous") or has_text(state["text"]):
        return "parse_cv"
    return "ocr_extract"


def ocr_extract(state: CvState) -> dict:
    """A scanned CV: read the page images with Tesseract."""
    with SessionLocal() as db:
        job_id = db.get(Candidate, state["candidate_id"]).job_id
    try:
        return {
            "text": ocr_text(find_cv(job_id, state["candidate_id"])),
            "used_ocr": True,
        }
    except UnreadableCv as exc:
        return {"error": str(exc)}


def after_ocr(state: CvState) -> str:
    """Route: error → log_and_skip; else parse_cv."""
    return "log_and_skip" if state.get("error") else "parse_cv"


def parse_cv(state: CvState) -> dict:
    """Structured data, the CV lines with embeddings (stored for later runs),
    and the applicant's name and email if the form did not give them.
    An unexpected problem with this CV skips it (the batch goes on); an AI
    service outage stops the run with a clear message (every CV needs it)."""
    try:
        return _parse_and_store(state)
    except AIServiceError:
        raise
    except Exception:
        logger.exception("CV could not be parsed: candidate %d", state["candidate_id"])
        return {"error": "This CV could not be processed."}


def after_parse(state: CvState) -> str:
    """Route: error → log_and_skip; else check_hard_requirements."""
    return "log_and_skip" if state.get("error") else "check_hard_requirements"


def _parse_and_store(state: CvState) -> dict:
    """The work of parse_cv (see there)."""
    today = datetime.now(UTC).date()
    previous = state.get("previous") or {}
    parsed = parse_cv_text(state["text"], today)
    parsed["text"] = state["text"]
    parsed["used_ocr"] = state.get("used_ocr", False)
    # The local model's earlier answers about requirements stay valid.
    parsed["model_checks"] = previous.get("model_checks", {})
    if parsed["years_source"] == "unknown":
        # No job dates the rules could read: ask the local model.
        answer = local_model.read_years(state["text"], today)
        if answer:
            parsed["years_experience"], parsed["years_evidence"] = answer
            parsed["years_source"] = "model"
    # The whole CV's embedding for the ATS score, stored for later runs.
    parsed["ats_vector"] = (
        previous.get("ats_vector")
        or embed_documents([state["text"][:MAX_CV_CHARS_FOR_ATS]])[0]
    )
    lines = cv_passages(parsed)
    same_lines = _stored_lines(state["candidate_id"]) == lines
    with SessionLocal() as db:
        candidate = db.get(Candidate, state["candidate_id"])
        if not same_lines:  # same lines as before: keep their embeddings
            vectors = embed_passages(lines)
            db.execute(delete(CvPassage).where(CvPassage.candidate_id == candidate.id))
            db.add_all(
                CvPassage(
                    candidate_id=candidate.id,
                    position=index,
                    section=section,
                    text=line,
                    embedding=vector,
                )
                for index, ((section, line), vector) in enumerate(
                    zip(lines, vectors, strict=True)
                )
            )
        if parsed["name"] and (not candidate.full_name or not candidate.drive_file_id):
            candidate.full_name = parsed["name"][:200]  # the CV beats a file-name guess
        candidate.email = candidate.email or parsed["email"]
        candidate.phone = candidate.phone or parsed["phone"]
        candidate.parsed_cv = parsed
        candidate.status = CandidateStatus.PARSED
        candidate.parse_error = None
        db.commit()
    return {"parsed": parsed}


def check_hard_requirements(state: CvState) -> dict:
    """Match the mandatory requirements and check the minimum years. Before
    excluding a candidate for a requirement the rules did not find, the local
    model checks the CV once more (only if the years are not too few anyway)."""
    context, parsed = state["context"], state["parsed"]
    years = known_years(parsed)
    mandatory = [r for r in context["requirements"] if r["level"] == "mandatory"]
    passages = _passages(state["candidate_id"])
    matches = match_requirements(
        mandatory, passages, years, context["requirement_vectors"]
    )
    failing = [m for m in matches if scoring.fails_mandatory(m)]
    if failing and not scoring.too_few_years(years, context["min_years"]):
        parsed = _second_opinion(state["candidate_id"], parsed, mandatory, failing)
        for match in failing:
            quote = parsed["model_checks"][_check_key(match["requirement"], mandatory)]
            if quote:
                _confirmed_by_model(match, quote, passages, years)
    reasons = scoring.check_gate(
        matches, years, context["min_years"], parsed.get("years_source", "dates")
    )
    return {"matches": matches, "gate_reasons": reasons, "parsed": parsed}


def after_gate(state: CvState) -> str:
    """Route: failed a must-have → record_exclusion; else match the rest."""
    return "record_exclusion" if state["gate_reasons"] else "match_requirements"


def match_requirements_node(state: CvState) -> dict:
    """Match the required and preferred requirements too."""
    others = [r for r in state["context"]["requirements"] if r["level"] != "mandatory"]
    more = match_requirements(
        others,
        _passages(state["candidate_id"]),
        known_years(state["parsed"]),
        state["context"]["requirement_vectors"],
    )
    return {"matches": state["matches"] + more}


def score_skills(state: CvState) -> dict:
    """Technical skills dimension."""
    score, reason = scoring.score_skills(state["matches"])
    return {"scores": {"skills": score}, "reasons": {"skills": reason}}


def score_experience(state: CvState) -> dict:
    """Relevant experience dimension."""
    parsed = state["parsed"]
    score, reason = scoring.score_experience(
        known_years(parsed),
        state["context"]["min_years"],
        parsed["jobs"],
        parsed.get("years_source", "dates"),
        parsed.get("years_evidence"),
    )
    return {"scores": {"experience": score}, "reasons": {"experience": reason}}


def score_qualifications(state: CvState) -> dict:
    """Academic and professional qualifications dimension."""
    score, reason = scoring.score_qualifications(
        state["parsed"]["degree"], state["matches"]
    )
    return {"scores": {"qualifications": score}, "reasons": {"qualifications": reason}}


def ats_match(state: CvState) -> dict:
    """ATS-style CV to job description match."""
    context, text = state["context"], state["parsed"]["text"]
    similarity = 0.0
    if context["jd_vector"]:
        cv_vector = (
            state["parsed"].get("ats_vector")
            or embed_documents([text[:MAX_CV_CHARS_FOR_ATS]])[0]
        )
        similarity = _cosine(context["jd_vector"], cv_vector)
    score, reason = scoring.score_ats(text, context["key_terms"], similarity)
    return {"scores": {"ats": score}, "reasons": {"ats": reason}}


def combine_scores(state: CvState) -> dict:
    """Weights × dimensions → overall 0-100, and this CV's result."""
    weights = state["context"]["weights"]
    overall = scoring.combine(state["scores"], weights)
    _count_progress(state["run_id"])
    return {
        "results": [
            {
                "candidate_id": state["candidate_id"],
                "outcome": "ranked",
                "overall": overall,
                "scores": state["scores"],
                "dimensions": scoring.dimension_rows(
                    state["scores"], state["reasons"], weights
                ),
                "matches": state["matches"],
                "summary": f"Overall {overall}/100.",
            }
        ]
    }


def record_exclusion(state: CvState) -> dict:
    """Failed a mandatory requirement: excluded, with the reasons (F1)."""
    _count_progress(state["run_id"])
    return {
        "results": [
            {
                "candidate_id": state["candidate_id"],
                "outcome": "excluded",
                "matches": state["matches"],
                "summary": " ".join(state["gate_reasons"]),
            }
        ]
    }


def log_and_skip(state: CvState) -> dict:
    """This CV could not be read: note why and go on with the batch."""
    with SessionLocal() as db:
        candidate = db.get(Candidate, state["candidate_id"])
        candidate.status = CandidateStatus.PARSE_FAILED
        candidate.parse_error = state["error"]
        db.commit()
    logger.warning("CV skipped in screening: candidate %d", state["candidate_id"])
    _count_progress(state["run_id"])
    return {
        "results": [
            {
                "candidate_id": state["candidate_id"],
                "outcome": "unreadable",
                "summary": state["error"],
            }
        ]
    }


# ---------- helpers ----------


def jd_plain_text(content: str) -> str:
    """The approved JD (stored as JSON) as plain text for the ATS score."""
    data = json.loads(content)
    parts = [
        data.get("title", ""),
        data.get("about", ""),
        *data.get("responsibilities", []),
    ]
    parts += [data.get("work_arrangement", ""), *data.get("what_we_offer", [])]
    return "\n".join(part for part in parts if part)


def run_weights(run_id: int) -> dict:
    """The weights recorded on the run when it was started."""
    with SessionLocal() as db:
        return dict(db.get(ScreeningRun, run_id).weights)


def key_terms(jd_text: str, requirements: list[dict]) -> list[str]:
    """The job's key terms for the ATS score: every requirement and its
    "also counts" names, plus the JD's most frequent meaningful words."""
    terms = []
    for requirement in requirements:
        terms.append(requirement["text"])
    words = re.findall(r"[A-Za-z][A-Za-z0-9+#.]{2,}", jd_text)
    counts = Counter(w.lower().rstrip(".") for w in words if w.lower() not in STOPWORDS)
    terms += [
        word for word, _count in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    unique = list(dict.fromkeys(term.lower() for term in terms))
    return unique[:KEY_TERM_COUNT]


def known_years(parsed: dict) -> float | None:
    """The CV's years of experience, or None when they could not be read."""
    if parsed.get("years_source") == "unknown":
        return None
    return parsed["years_experience"]


def _check_key(requirement_text: str, requirements: list[dict]) -> str:
    """Cache key of a local-model check: the model, the requirement and its
    "also counts" names (a changed profile or model asks again)."""
    requirement = next(r for r in requirements if r["text"] == requirement_text)
    names = "|".join(requirement.get("also_counts", []))
    return f"{get_settings().screening_model}|{requirement_text}|{names}"


def _second_opinion(
    candidate_id: int, parsed: dict, mandatory: list[dict], failing: list[dict]
) -> dict:
    """Ask the local model about the failing requirements it was not asked
    about before; its answers are stored with the parsed CV for later runs."""
    checks = dict(parsed.get("model_checks", {}))
    texts = {m["requirement"] for m in failing}
    todo = [
        r
        for r in mandatory
        if r["text"] in texts and _check_key(r["text"], mandatory) not in checks
    ]
    if not todo:
        return parsed
    answers = local_model.confirm_requirements(parsed["text"], todo)
    for requirement in todo:
        checks[_check_key(requirement["text"], mandatory)] = answers[
            requirement["text"]
        ]
    parsed = {**parsed, "model_checks": checks}
    with SessionLocal() as db:
        db.get(Candidate, candidate_id).parsed_cv = parsed
        db.commit()
    return parsed


def _confirmed_by_model(
    match: dict, quote: str, passages: list, years: float | None
) -> None:
    """The local model found a real CV line for the requirement: met, with
    that line as the evidence ("5 years of PHP" still needs the years)."""
    line = local_model.normalised(quote)
    section = next(
        (
            s
            for s, text, _v in passages
            if line in local_model.normalised(text)
            or local_model.normalised(text) in line
        ),
        None,
    )
    match.update(
        status="partial" if too_few_years(match["requirement"], years) else "met",
        decided_by="local_model",
        matched_name=None,
        evidence=quote,
        section=section,
    )


def _stored_lines(candidate_id: int) -> list[tuple[str, str]]:
    """The CV lines stored for this candidate (to reuse their embeddings)."""
    return [(section, text) for section, text, _v in _passages(candidate_id)]


def _passages(candidate_id: int) -> list[tuple[str, str, list[float]]]:
    """The stored CV lines with their embeddings."""
    with SessionLocal() as db:
        rows = db.scalars(
            select(CvPassage)
            .where(CvPassage.candidate_id == candidate_id)
            .order_by(CvPassage.position)
        )
        return [(p.section, p.text, list(p.embedding)) for p in rows]


def _count_progress(run_id: int) -> None:
    """One more CV done ("12 of 20" on screen, N25)."""
    with SessionLocal() as db:
        db.execute(
            update(ScreeningRun)
            .where(ScreeningRun.id == run_id)
            .values(processed=ScreeningRun.processed + 1)
        )
        db.commit()


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two vectors."""
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
    return dot / norm if norm else 0.0


# ---------- building and running ----------


def build_screen_cv():
    """The per-CV subgraph (one branch of the batch)."""
    graph = StateGraph(CvState, output_schema=CvOutput)
    graph.add_node("extract_text", extract_text)
    graph.add_node("ocr_extract", ocr_extract)
    graph.add_node("parse_cv", parse_cv)
    graph.add_node("check_hard_requirements", check_hard_requirements)
    graph.add_node("match_requirements", match_requirements_node)
    for name, node in [
        ("score_skills", score_skills),
        ("score_experience", score_experience),
        ("score_qualifications", score_qualifications),
        ("ats_match", ats_match),
    ]:
        graph.add_node(name, node)
    graph.add_node("combine_scores", combine_scores)
    graph.add_node("record_exclusion", record_exclusion)
    graph.add_node("log_and_skip", log_and_skip)

    graph.add_edge(START, "extract_text")
    graph.add_conditional_edges(
        "extract_text",
        after_extract,
        ["parse_cv", "ocr_extract", "log_and_skip", "check_hard_requirements"],
    )
    graph.add_conditional_edges("ocr_extract", after_ocr, ["parse_cv", "log_and_skip"])
    graph.add_conditional_edges(
        "parse_cv", after_parse, ["check_hard_requirements", "log_and_skip"]
    )
    graph.add_conditional_edges(
        "check_hard_requirements",
        after_gate,
        ["record_exclusion", "match_requirements"],
    )
    scorers = ["score_skills", "score_experience", "score_qualifications", "ats_match"]
    for name in scorers:  # the four dimensions run in parallel
        graph.add_edge("match_requirements", name)
    graph.add_edge(scorers, "combine_scores")  # waits for all four
    for name in ("combine_scores", "record_exclusion", "log_and_skip"):
        graph.add_edge(name, END)
    return graph.compile()


def build_cv_screening(checkpointer):
    """The whole screening workflow, checkpointed in PostgreSQL."""
    graph = StateGraph(ScreeningState)
    graph.add_node("load_cv_batch", load_cv_batch)
    graph.add_node("screen_cv", build_screen_cv())
    graph.add_node("collect_results", collect_results)
    graph.add_node("rank_candidates", rank_candidates)
    graph.add_node("save_results", save_results)
    graph.add_edge(START, "load_cv_batch")
    graph.add_conditional_edges(
        "load_cv_batch", send_cvs, ["screen_cv", "collect_results"]
    )
    graph.add_edge("screen_cv", "collect_results")
    graph.add_edge("collect_results", "rank_candidates")
    graph.add_edge("rank_candidates", "save_results")
    graph.add_edge("save_results", END)
    return graph.compile(checkpointer=checkpointer)


def run_screening(run_id: int) -> None:
    """Work function for the background runner: run (or continue) one
    screening run. A run that stopped half-way continues from its last
    checkpoint instead of starting again (N26)."""
    config = graph_config(RUN_KIND, run_id)
    config["recursion_limit"] = 50
    with open_checkpointer() as checkpointer:
        graph = build_cv_screening(checkpointer)
        started = graph.get_state(config).next
        graph.invoke(None if started else {"run_id": run_id, "results": []}, config)


register_run_kind(RUN_KIND, ScreeningRun, run_screening)
