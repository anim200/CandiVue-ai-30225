r"""LangGraph 3: Interview Q&A Analysis (Figure 5). A fixed workflow, started
when an interview ends, so the evaluation is repeatable and traceable.

    START → load_transcript_and_requirements → segment_qa_pairs
          ─ Send: one evaluate_qa_pair branch per Q&A unit, in parallel
    evaluate_qa_pair:
        classify_question ─ job ─────→ retrieve_reference_docs ─┐
                          ├ company ─→ retrieve_company_docs ───┴→ evaluate_against_docs
                          └ other ───→ mark_not_scored
    → merge_evaluations → map_to_requirements → find_unexplored_requirements
    → save_qa_analysis → END

- The whole conversation is kept; only answered job- and company-related
  questions are scored (trainer clarification). Multi-part questions and
  follow-ups are separate units (app/analysis/qa_pairs.py).
- Both kinds of answers are checked against documents through RAG (user
  decision 17-10-2026, replacing §4B-5's "LLM only" for job answers): job
  answers against the Reference library (authoritative documentation),
  company answers against Company policies. Without a matching passage the
  LLM judges alone and the pair is marked "not checked against a document".
- State is checkpointed in PostgreSQL: after a failure (e.g. the daily AI
  limit) "Try again" continues; units already evaluated are not sent to
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
from app.analysis.prompts import COMPANY_NOTE, EVALUATE_PROMPT, SEGMENT_PROMPT
from app.analysis.transcript import Line, load_lines
from app.core import clock
from app.db.database import SessionLocal
from app.db.models import InterviewSession, Job, QAAnalysis
from app.db.models.knowledge import KnowledgeCollection
from app.db.models.run import RunStatus
from app.graphs import final_assessment
from app.graphs.checkpointer import forget_thread, open_checkpointer
from app.knowledge.search import search_knowledge
from app.runs.runner import graph_config, register_run_kind, start_run

logger = logging.getLogger(__name__)

RUN_KIND = "qa_analysis"
# The transcriber saves the last words a few seconds after the end.
TRANSCRIPT_SETTLE_SECONDS = 15
MAX_PARALLEL = 4  # Q&A units evaluated at once (stays under per-minute AI limits)
PASSAGES_PER_ANSWER = 4
MIN_PASSAGE_SCORE = 0.5  # weaker matches are not about the same topic
MAX_PASSAGE_CHARS = 900
MAX_QUERY_CHARS = 600


class AnalysisState(TypedDict, total=False):
    """The whole interview: the job, the Q&A units and their evaluations."""

    analysis_id: int
    session_id: int
    job: dict  # title and requirements
    pairs: list[dict]
    evaluated: Annotated[list[dict], operator.add]  # one per unit, from the branches
    coverage: list[dict]
    unexplored: list[str]


class PairState(TypedDict, total=False):
    """One Q&A unit's branch (evaluate_qa_pair subgraph)."""

    analysis_id: int
    session_id: int
    job: dict
    pair: dict
    follows: str | None  # the question a follow-up looks back to
    passages: list[dict]
    evaluated: Annotated[list[dict], operator.add]


class PairOutput(TypedDict):
    """What one branch hands back: only its evaluation."""

    evaluated: Annotated[list[dict], operator.add]


# ---------- the whole interview ----------


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
    """Split the transcript into question–answer units (one LLM request)."""
    lines = _lines(state["session_id"])
    pairs = []
    if lines:
        answer = invoke_llm(
            [
                SystemMessage(SEGMENT_PROMPT),
                HumanMessage(
                    f"Job: {state['job']['title']}\n"
                    f"Job requirements:\n{_numbered(state['job']['requirements'])}\n\n"
                    "Transcript:\n" + "\n".join(line.as_prompt() for line in lines)
                ),
            ],
            prepare=lambda model: model.with_structured_output(qa_pairs.Segmentation),
        )
        pairs = qa_pairs.build_pairs(answer.units, lines)
    _set_progress(
        state["analysis_id"], processed=0, total=sum(map(qa_pairs.is_scored, pairs))
    )
    logger.info("Q&A units found: analysis %d (%d)", state["analysis_id"], len(pairs))
    return {"pairs": pairs}


def send_pairs(state: AnalysisState) -> list[Send]:
    """Fan out: one evaluate_qa_pair branch per unit, run in parallel."""
    questions = {pair["id"]: pair["question"] for pair in state["pairs"]}
    return [
        Send(
            "evaluate_qa_pair",
            {
                "analysis_id": state["analysis_id"],
                "session_id": state["session_id"],
                "job": state["job"],
                "pair": pair,
                "follows": questions.get(pair["follow_up_of"]),
            },
        )
        for pair in state["pairs"]
    ] or [Send("merge_evaluations", state)]


def merge_evaluations(state: AnalysisState) -> dict:
    """All branches are back: put the units in the order they were asked."""
    order = {pair["id"]: i for i, pair in enumerate(state.get("pairs", []))}
    merged = sorted(state.get("evaluated", []), key=lambda pair: order[pair["id"]])
    return {"pairs": merged}


def map_to_requirements(state: AnalysisState) -> dict:
    """Each job requirement with the units that explored it."""
    return {"coverage": qa_pairs.coverage(state["job"]["requirements"], state["pairs"])}


def find_unexplored_requirements(state: AnalysisState) -> dict:
    """The requirements no unit explored: gaps for the interviewer to see."""
    return {
        "unexplored": [c["requirement"] for c in state["coverage"] if not c["pair_ids"]]
    }


def save_qa_analysis(state: AnalysisState) -> dict:
    """Save the units, their evaluations and the requirement coverage."""
    pairs = [
        {key: value for key, value in pair.items() if key != "lines"}
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
            "model": current_model(),
            "analysed_at": clock.now().isoformat(),
        }
        analysis.processed = analysis.total = scored
        db.commit()
    logger.info("Q&A analysis %d saved: %d scored", state["analysis_id"], scored)
    return {}


# ---------- one Q&A unit (evaluate_qa_pair subgraph) ----------


def classify_question(state: PairState) -> str:
    """Route by kind: job and company answers are evaluated against their
    documents; small talk and unanswered questions are not scored."""
    pair = state["pair"]
    if not qa_pairs.is_scored(pair):
        return "mark_not_scored"
    return (
        "retrieve_company_docs"
        if pair["kind"] == "company"
        else "retrieve_reference_docs"
    )


def retrieve_reference_docs(state: PairState) -> dict:
    """Find authoritative documentation on the answer's topic (RAG)."""
    return {"passages": _passages(state, KnowledgeCollection.REFERENCE_LIBRARY)}


def retrieve_company_docs(state: PairState) -> dict:
    """Find the company documents the answer should match (RAG)."""
    return {"passages": _passages(state, KnowledgeCollection.COMPANY_POLICIES)}


def evaluate_against_docs(state: PairState) -> dict:
    """Score the answer on relevance, accuracy, completeness and
    articulation (one LLM request), then check what the LLM returned."""
    pair, job = state["pair"], state["job"]
    passages = state.get("passages", [])
    context = []
    if pair.get("part"):
        context.append(
            f"(Part {pair['part'][0]} of {pair['part'][1]} of a multi-part question.)"
        )
    if state.get("follows"):
        context.append(f'(A follow-up to the earlier question: "{state["follows"]}")')
    documents = "\n\n".join(
        f"[{n}] {p['filename']}:\n{p['excerpt']}"
        for n, p in enumerate(passages, start=1)
    )
    answer = invoke_llm(
        [
            SystemMessage(
                EVALUATE_PROMPT.format(
                    company_note=COMPANY_NOTE if pair["kind"] == "company" else ""
                )
            ),
            HumanMessage(
                f"Job: {job['title']}\nJob requirements:\n{_numbered(job['requirements'])}\n\n"
                f"Question: {pair['question']} {' '.join(context)}\n\n"
                "Transcript lines:\n"
                + "\n".join(
                    line.as_prompt()
                    for line in _lines(state["session_id"])
                    if line.number in pair["lines"]
                )
                + f"\n\nReference passages:\n{documents or '(none found)'}"
            ),
        ],
        prepare=lambda model: model.with_structured_output(qa_pairs.Evaluation),
    )
    evaluated = qa_pairs.apply_evaluation(pair, answer, job["requirements"], passages)
    _count_progress(state["analysis_id"])
    return {"evaluated": [evaluated]}


def mark_not_scored(state: PairState) -> dict:
    """Keep the unit (the whole conversation is kept) without scores."""
    return {"evaluated": [qa_pairs.not_scored(state["pair"])]}


# ---------- helpers ----------


def _lines(session_id: int) -> list[Line]:
    """The interview's numbered transcript lines (read again in each step,
    so the checkpointed state stays small)."""
    with SessionLocal() as db:
        return load_lines(db, db.get(InterviewSession, session_id))


def _numbered(requirements: list[dict]) -> str:
    """Requirements as a numbered list, e.g. "1. PHP (mandatory)"."""
    return (
        "\n".join(
            f"{n}. {r['text']} ({r['level']})"
            for n, r in enumerate(requirements, start=1)
        )
        or "(none saved)"
    )


def _passages(state: PairState, collection: KnowledgeCollection) -> list[dict]:
    """The passages of one knowledge-base collection closest to this
    question and answer; weak matches are left out."""
    pair = state["pair"]
    answer = " ".join(
        line.text
        for line in _lines(state["session_id"])
        if line.turn_id in pair["answer_turn_ids"]
    )
    query = f"{pair['question']} {answer}"[:MAX_QUERY_CHARS]
    with SessionLocal() as db:
        found = search_knowledge(db, query, [collection], PASSAGES_PER_ANSWER)
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


def _set_progress(analysis_id: int, processed: int, total: int) -> None:
    """Save how many units are evaluated, of how many ("4 of 7", N25)."""
    with SessionLocal() as db:
        analysis = db.get(QAAnalysis, analysis_id)
        analysis.processed, analysis.total = processed, total
        db.commit()


def _count_progress(analysis_id: int) -> None:
    """One more unit evaluated."""
    with SessionLocal() as db:
        db.execute(
            update(QAAnalysis)
            .where(QAAnalysis.id == analysis_id)
            .values(processed=QAAnalysis.processed + 1)
        )
        db.commit()


# ---------- building, running and starting ----------


def build_evaluate_qa_pair():
    """The per-unit subgraph (one branch of the fan-out)."""
    graph = StateGraph(PairState, output_schema=PairOutput)
    graph.add_node("retrieve_reference_docs", retrieve_reference_docs)
    graph.add_node("retrieve_company_docs", retrieve_company_docs)
    graph.add_node("evaluate_against_docs", evaluate_against_docs)
    graph.add_node("mark_not_scored", mark_not_scored)
    graph.add_conditional_edges(
        START,
        classify_question,
        ["retrieve_reference_docs", "retrieve_company_docs", "mark_not_scored"],
    )
    graph.add_edge("retrieve_reference_docs", "evaluate_against_docs")
    graph.add_edge("retrieve_company_docs", "evaluate_against_docs")
    graph.add_edge("evaluate_against_docs", END)
    graph.add_edge("mark_not_scored", END)
    return graph.compile()


def build_qa_analysis(checkpointer):
    """The whole Q&A analysis workflow, checkpointed in PostgreSQL."""
    graph = StateGraph(AnalysisState)
    graph.add_node("load_transcript_and_requirements", load_transcript_and_requirements)
    graph.add_node("segment_qa_pairs", segment_qa_pairs)
    graph.add_node("evaluate_qa_pair", build_evaluate_qa_pair())
    graph.add_node("merge_evaluations", merge_evaluations)
    graph.add_node("map_to_requirements", map_to_requirements)
    graph.add_node("find_unexplored_requirements", find_unexplored_requirements)
    graph.add_node("save_qa_analysis", save_qa_analysis)
    graph.add_edge(START, "load_transcript_and_requirements")
    graph.add_edge("load_transcript_and_requirements", "segment_qa_pairs")
    graph.add_conditional_edges(
        "segment_qa_pairs", send_pairs, ["evaluate_qa_pair", "merge_evaluations"]
    )
    graph.add_edge("evaluate_qa_pair", "merge_evaluations")
    graph.add_edge("merge_evaluations", "map_to_requirements")
    graph.add_edge("map_to_requirements", "find_unexplored_requirements")
    graph.add_edge("find_unexplored_requirements", "save_qa_analysis")
    graph.add_edge("save_qa_analysis", END)
    return graph.compile(checkpointer=checkpointer)


def run_qa_analysis(analysis_id: int) -> None:
    """Work function for the background runner: run (or continue) one
    analysis, then start the interview's assessment report."""
    config = graph_config(RUN_KIND, analysis_id)
    config |= {"recursion_limit": 100, "max_concurrency": MAX_PARALLEL}
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
