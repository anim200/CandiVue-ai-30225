r"""LangGraph 3: Interview Q&A Analysis (Figure 5). A fixed workflow, started
when an interview ends, so the evaluation is repeatable and traceable.

    START → load_transcript_and_requirements → segment_qa_pairs   (1 AI request)
          → retrieve_documents          (RAG per answer: local, no AI request)
          ─ Send: one evaluate_answers branch per batch of up to 20 answers
                                        (1 AI request per batch, usually one)
          → merge_evaluations → map_to_requirements → find_unexplored_requirements
          → review_interview            (1 AI request: CV claims F8, two F9
                                         judgements, advice for the interviewer F10)
          → score_interview (F9) → assess_interview_quality (F10)   (plain code)
          → save_qa_analysis → END

- The whole conversation is kept; only answered job- and company-related
  questions are scored (trainer clarification). Multi-part questions and
  follow-ups are separate units (app/analysis/qa_pairs.py).
- Both kinds of answers are checked against documents through RAG (user
  decision 17-10-2026): job answers against the Reference library
  (authoritative documentation), company answers against Company policies.
  Without a matching passage the LLM judges alone and the answer is marked
  "not checked against a document".
- Few AI requests (free-tier limits): about 3 per interview instead of one
  per answer (README "AI usage"). Everything the AI returns is checked in
  code against the transcript and the CV before it is kept.
- State is checkpointed in PostgreSQL: after a failure (e.g. the daily AI
  limit) "Try again" continues; finished steps and batches are not sent to
  the LLM again (N26).
- When it finishes, the consolidated assessment (LangGraph 4) starts (B5).
"""

import logging
import operator
import time
from typing import Annotated, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai.llm import invoke_llm
from app.ai.usage import current_model
from app.analysis import qa_pairs
from app.analysis.assessment import cv_items
from app.analysis.interview_quality import interview_quality
from app.analysis.interview_score import interview_score
from app.analysis.prompts import EVALUATE_PROMPT, REVIEW_PROMPT, SEGMENT_PROMPT
from app.analysis.review import MAX_CLAIMS, InterviewReview, check_review
from app.analysis.transcript import Line, clock_text, load_lines
from app.core import clock
from app.db.database import SessionLocal
from app.db.models import Candidate, InterviewSession, Job, QAAnalysis
from app.db.models.knowledge import KnowledgeCollection
from app.db.models.run import RunStatus
from app.graphs import final_assessment
from app.graphs.checkpointer import forget_thread, open_checkpointer
from app.interviews.cv_view import screening_result
from app.knowledge.search import search_knowledge
from app.runs.runner import graph_config, register_run_kind, start_run

logger = logging.getLogger(__name__)

RUN_KIND = "qa_analysis"
# The transcriber saves the last words a few seconds after the end.
TRANSCRIPT_SETTLE_SECONDS = 15
EVALUATE_BATCH = 20  # answers per AI request (a typical interview: one request)
PASSAGES_PER_ANSWER = 4
MIN_PASSAGE_SCORE = 0.5  # weaker matches are not about the same topic
MAX_PASSAGE_CHARS = 900
MAX_QUERY_CHARS = 600
COLLECTIONS = {
    "job": KnowledgeCollection.REFERENCE_LIBRARY,
    "company": KnowledgeCollection.COMPANY_POLICIES,
}


class AnalysisState(TypedDict, total=False):
    """The whole interview: the job, the Q&A units, their evaluations and
    the interview-level results (F8-F10)."""

    analysis_id: int
    session_id: int
    job: dict  # title and requirements
    pairs: list[dict]
    evaluated: Annotated[list[dict], operator.add]  # from the batch branches
    coverage: list[dict]
    unexplored: list[str]
    review: dict | None
    interview_score: dict | None
    quality: dict


class BatchState(TypedDict):
    """One batch of answers to evaluate (evaluate_answers branch)."""

    analysis_id: int
    session_id: int
    job: dict
    batch: list[dict]
    questions: dict[str, str]  # every unit's question, for follow-ups


# ---------- steps ----------


def load_transcript_and_requirements(state: AnalysisState) -> dict:
    """Read the interview's job requirements; first give the transcriber a
    moment to save the last words after the end."""
    with SessionLocal() as db:
        analysis = db.get(QAAnalysis, state["analysis_id"])
        session = db.get(InterviewSession, analysis.session_id)
        job = db.get(Job, session.job_id)
        ended_at = session.ended_at or clock.now()
        requirements = [
            {"text": r["text"], "level": r.get("level", "mandatory")}
            for r in (job.profile or {}).get("requirements", [])
        ]
        job_context = {"title": job.title, "requirements": requirements}
    wait = TRANSCRIPT_SETTLE_SECONDS - (clock.now() - ended_at).total_seconds()
    if wait > 0:
        time.sleep(wait)
    return {"session_id": session.id, "job": job_context}


def segment_qa_pairs(state: AnalysisState) -> dict:
    """Split the transcript into question–answer units (one AI request)."""
    lines = _lines(state["session_id"])
    pairs = []
    if lines:
        answer = invoke_llm(
            [
                SystemMessage(SEGMENT_PROMPT),
                HumanMessage(
                    f"{_job_text(state['job'])}\n\nTranscript:\n"
                    + "\n".join(line.as_prompt() for line in lines)
                ),
            ],
            prepare=lambda model: model.with_structured_output(qa_pairs.Segmentation),
        )
        pairs = qa_pairs.build_pairs(answer.units, lines)
    logger.info("Q&A units found: analysis %d (%d)", state["analysis_id"], len(pairs))
    return {"pairs": pairs}


def retrieve_documents(state: AnalysisState) -> dict:
    """RAG for every answer to score: job answers search the Reference
    library, company answers the Company policies (local search, no AI
    request). Small talk and unanswered questions are marked not scored."""
    lines = _lines(state["session_id"])
    pairs = [
        pair | {"passages": _passages(pair, lines)}
        if qa_pairs.is_scored(pair)
        else qa_pairs.not_scored(pair)
        for pair in state["pairs"]
    ]
    _set_progress(state["analysis_id"], total=sum(map(qa_pairs.is_scored, pairs)))
    return {"pairs": pairs}


def send_batches(state: AnalysisState) -> list[Send]:
    """Fan out: one evaluate_answers branch per batch of answers."""
    to_score = [p for p in state["pairs"] if qa_pairs.is_scored(p)]
    questions = {pair["id"]: pair["question"] for pair in state["pairs"]}
    return [
        Send(
            "evaluate_answers",
            {
                "analysis_id": state["analysis_id"],
                "session_id": state["session_id"],
                "job": state["job"],
                "batch": to_score[start : start + EVALUATE_BATCH],
                "questions": questions,
            },
        )
        for start in range(0, len(to_score), EVALUATE_BATCH)
    ] or [Send("merge_evaluations", state)]


def evaluate_answers(state: BatchState) -> dict:
    """Score a batch of answers on relevance, accuracy, completeness and
    articulation (one AI request), then check what came back."""
    lines = {line.number: line for line in _lines(state["session_id"])}
    units = "\n\n".join(
        _unit_text(pair, lines, state["questions"]) for pair in state["batch"]
    )
    answer = invoke_llm(
        [
            SystemMessage(EVALUATE_PROMPT),
            HumanMessage(f"{_job_text(state['job'])}\n\n{units}"),
        ],
        prepare=lambda model: model.with_structured_output(qa_pairs.Evaluations),
    )
    by_unit = {evaluation.unit: evaluation for evaluation in answer.evaluations}
    requirements = state["job"]["requirements"]
    evaluated = [
        qa_pairs.apply_evaluation(
            pair, by_unit[pair["id"]], requirements, pair["passages"]
        )
        for pair in state["batch"]
        if pair["id"] in by_unit
    ]
    _count_progress(state["analysis_id"], len(state["batch"]))
    return {"evaluated": evaluated}


def merge_evaluations(state: AnalysisState) -> dict:
    """All batches are back: every unit in the order asked, with its
    evaluation (an answer the AI skipped is shown as not scored)."""
    evaluated = {pair["id"]: pair for pair in state.get("evaluated", [])}
    return {
        "pairs": [
            evaluated.get(pair["id"]) or qa_pairs.not_scored(pair, "missing")
            if qa_pairs.is_scored(pair)
            else pair
            for pair in state.get("pairs", [])
        ]
    }


def map_to_requirements(state: AnalysisState) -> dict:
    """Each job requirement with the units that explored it."""
    return {"coverage": qa_pairs.coverage(state["job"]["requirements"], state["pairs"])}


def find_unexplored_requirements(state: AnalysisState) -> dict:
    """The requirements no unit explored: gaps for the interviewer to see."""
    return {
        "unexplored": [c["requirement"] for c in state["coverage"] if not c["pair_ids"]]
    }


def review_interview(state: AnalysisState) -> dict:
    """One AI request over the whole interview: CV claims compared with the
    answers (F8), problem-solving and experience depth (F9), questions that
    gave little evidence and suggestions (F10); then checked against the CV
    and the transcript. Skipped (no request) when no answer was scored."""
    if not any(p["status"] == "scored" for p in state["pairs"]):
        return {"review": None}
    with SessionLocal() as db:
        session = db.get(InterviewSession, state["session_id"])
        candidate = db.get(Candidate, session.candidate_id)
        result = screening_result(db, db.get(Job, session.job_id), candidate.id)
        cv = cv_items(candidate, (result or {}).get("matches", []))
        lines = load_lines(db, session)
    answer = invoke_llm(
        [
            SystemMessage(REVIEW_PROMPT.format(max_claims=MAX_CLAIMS)),
            HumanMessage(
                f"{_job_text(state['job'])}\n\n"
                "CV items (data):\n"
                + (
                    "\n".join(f"{i} ({c['label']}): {c['text']}" for i, c in cv.items())
                    or "(none)"
                )
                + "\n\nQ&A units:\n"
                + "\n".join(_scored_line(pair) for pair in state["pairs"])
                + "\n\nTranscript:\n"
                + "\n".join(line.as_prompt() for line in lines)
            ),
        ],
        prepare=lambda model: model.with_structured_output(InterviewReview),
    )
    return {"review": check_review(answer, cv, lines, state["pairs"])}


def score_interview(state: AnalysisState) -> dict:
    """The interview score on six dimensions (F9, plain code)."""
    judged = (state.get("review") or {}).get("judged", {})
    return {
        "interview_score": interview_score(state["pairs"], state["coverage"], judged)
    }


def assess_interview_quality(state: AnalysisState) -> dict:
    """How good the interview was as evidence (F10, plain code)."""
    lines = _lines(state["session_id"])
    return {
        "quality": interview_quality(
            state["pairs"], state["coverage"], lines, state.get("review")
        )
    }


def save_qa_analysis(state: AnalysisState) -> dict:
    """Save the units, their evaluations, the requirement coverage, the CV
    claims, the interview score and the interview quality."""
    pairs = [
        {key: value for key, value in pair.items() if key not in ("lines", "passages")}
        for pair in state["pairs"]
    ]
    scored = sum(pair["status"] == "scored" for pair in pairs)
    with SessionLocal() as db:
        analysis = db.get(QAAnalysis, state["analysis_id"])
        analysis.results = {
            "pairs": pairs,
            "coverage": state["coverage"],
            "unexplored": state["unexplored"],
            "scored": scored,
            "claims": (state.get("review") or {}).get("claims", []),
            "interview_score": state["interview_score"],
            "quality": state["quality"],
            "model": current_model(),
            "analysed_at": clock.now().isoformat(),
        }
        analysis.processed = analysis.total = scored
        db.commit()
    logger.info("Q&A analysis %d saved: %d scored", state["analysis_id"], scored)
    return {}


# ---------- helpers ----------


def _lines(session_id: int) -> list[Line]:
    """The interview's numbered transcript lines (read again in each step,
    so the checkpointed state stays small)."""
    with SessionLocal() as db:
        return load_lines(db, db.get(InterviewSession, session_id))


def _job_text(job: dict) -> str:
    """The job and its numbered requirements, e.g. "1. PHP (mandatory)"."""
    requirements = "\n".join(
        f"{n}. {r['text']} ({r['level']})"
        for n, r in enumerate(job["requirements"], start=1)
    )
    return f"Job: {job['title']}\nJob requirements:\n{requirements or '(none saved)'}"


def _unit_text(pair: dict, lines: dict[int, Line], questions: dict[str, str]) -> str:
    """One unit as the evaluation request reads it: id, kind, question,
    its transcript lines and its numbered reference passages."""
    notes = [f"{pair['kind']} question"]
    if pair.get("part"):
        notes.append(
            f"part {pair['part'][0]} of {pair['part'][1]} of a multi-part question"
        )
    if pair.get("follow_up_of"):
        earlier = pair["follow_up_of"]
        notes.append(f'follow-up to {earlier}: "{questions.get(earlier, "")}"')
    passages = "\n".join(
        f"[{n}] {p['filename']}: {p['excerpt']}"
        for n, p in enumerate(pair["passages"], start=1)
    )
    return (
        f"Unit {pair['id']} ({'; '.join(notes)})\nQuestion: {pair['question']}\n"
        "Transcript lines:\n"
        + "\n".join(lines[n].as_prompt() for n in pair["lines"] if n in lines)
        + f"\nReference passages:\n{passages or '(none found)'}"
    )


def _scored_line(pair: dict) -> str:
    """A unit for the review request, e.g. 'Q2a [00:15] "..." L3-L4 · accuracy 80'."""
    head = f'{pair["id"]} [{clock_text(pair["start_ms"])}] "{pair["question"]}" lines {pair["lines"]}'
    if pair["status"] != "scored":
        return f"{head} · not scored"
    return (
        head
        + " · "
        + ", ".join(
            f"{name} {pair['scores'][name]['score']}" for name in qa_pairs.DIMENSIONS
        )
    )


def _passages(pair: dict, lines: list[Line]) -> list[dict]:
    """The passages of the right collection closest to this question and
    answer; weak matches are left out."""
    answer = " ".join(
        line.text for line in lines if line.turn_id in pair["answer_turn_ids"]
    )
    query = f"{pair['question']} {answer}"[:MAX_QUERY_CHARS]
    with SessionLocal() as db:
        found = search_knowledge(
            db, query, [COLLECTIONS[pair["kind"]]], PASSAGES_PER_ANSWER
        )
    return [
        {
            "document_id": p.document_id,
            "filename": p.filename,
            "collection": str(p.collection),
            "excerpt": p.text[:MAX_PASSAGE_CHARS],
        }
        for p in found
        if p.score >= MIN_PASSAGE_SCORE
    ]


def _set_progress(analysis_id: int, total: int) -> None:
    """Save how many answers are to be evaluated ("0 of 7", N25)."""
    with SessionLocal() as db:
        analysis = db.get(QAAnalysis, analysis_id)
        analysis.processed, analysis.total = 0, total
        db.commit()


def _count_progress(analysis_id: int, done: int) -> None:
    """A batch of answers is evaluated."""
    with SessionLocal() as db:
        db.execute(
            update(QAAnalysis)
            .where(QAAnalysis.id == analysis_id)
            .values(processed=QAAnalysis.processed + done)
        )
        db.commit()


# ---------- building, running and starting ----------


def build_qa_analysis(checkpointer):
    """The whole Q&A analysis workflow, checkpointed in PostgreSQL."""
    graph = StateGraph(AnalysisState)
    for step in (
        load_transcript_and_requirements,
        segment_qa_pairs,
        retrieve_documents,
        evaluate_answers,
        merge_evaluations,
        map_to_requirements,
        find_unexplored_requirements,
        review_interview,
        score_interview,
        assess_interview_quality,
        save_qa_analysis,
    ):
        graph.add_node(step.__name__, step)
    graph.add_edge(START, "load_transcript_and_requirements")
    graph.add_edge("load_transcript_and_requirements", "segment_qa_pairs")
    graph.add_edge("segment_qa_pairs", "retrieve_documents")
    graph.add_conditional_edges(
        "retrieve_documents", send_batches, ["evaluate_answers", "merge_evaluations"]
    )
    graph.add_edge("evaluate_answers", "merge_evaluations")
    graph.add_edge("merge_evaluations", "map_to_requirements")
    graph.add_edge("map_to_requirements", "find_unexplored_requirements")
    graph.add_edge("find_unexplored_requirements", "review_interview")
    graph.add_edge("review_interview", "score_interview")
    graph.add_edge("score_interview", "assess_interview_quality")
    graph.add_edge("assess_interview_quality", "save_qa_analysis")
    graph.add_edge("save_qa_analysis", END)
    return graph.compile(checkpointer=checkpointer)


def run_qa_analysis(analysis_id: int) -> None:
    """Work function for the background runner: run (or continue) one
    analysis, then start the interview's assessment report."""
    config = graph_config(RUN_KIND, analysis_id)
    config["recursion_limit"] = 60
    with open_checkpointer() as checkpointer:
        graph = build_qa_analysis(checkpointer)
        started = graph.get_state(config).next
        graph.invoke(
            None if started else {"analysis_id": analysis_id, "evaluated": []}, config
        )
    with SessionLocal() as db:
        session_id = db.get(QAAnalysis, analysis_id).session_id
        final_assessment.start_report(db, session_id)


def start_analysis(db: Session, session_id: int, again: bool = False) -> QAAnalysis:
    """Start the Q&A analysis of an ended interview, continue a failed one,
    or (again=True) analyse it afresh. Analysing afresh replaces the
    interview's assessment report too: it would rest on the old analysis."""
    analysis = db.scalar(select(QAAnalysis).where(QAAnalysis.session_id == session_id))
    if analysis is not None and analysis.status == RunStatus.FAILED and not again:
        analysis.status, analysis.error = RunStatus.PENDING, None
        db.commit()
        start_run(RUN_KIND, analysis.id)
        return analysis
    if analysis is not None and not again:
        return analysis
    if analysis is not None:
        forget_thread(graph_config(RUN_KIND, analysis.id))
        db.delete(analysis)
        final_assessment.remove_reports(db, session_id)
        db.flush()
    analysis = QAAnalysis(session_id=session_id)
    db.add(analysis)
    db.commit()
    start_run(RUN_KIND, analysis.id)
    logger.info(
        "Q&A analysis started: session %d, analysis %d", session_id, analysis.id
    )
    return analysis


register_run_kind(RUN_KIND, QAAnalysis, run_qa_analysis)
