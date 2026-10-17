r"""Talent rediscovery (F11, innovation feature): the job's talent pool,
screened against the job with LangGraph 2's own per-CV subgraph.

    START → load_pool ─ Send: one screen_cv branch per past application
          → collect_results → save_matches → END

- Runs after the job's screening finishes, and again on "Check again".
- No new AI and nothing leaves the machine: the same local parsing,
  matching, gate and scores as screening (parsed CVs and their embeddings
  are reused). Only applications that pass the job's mandatory
  requirements and reach SHOW_FROM are saved as matches.
- Matches are stored apart from screening runs, so they never mix into the
  job's own ranking. Checkpointed like every run (N26).
"""

import logging
import operator
from typing import Annotated, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from sqlalchemy import delete

from app.db.database import SessionLocal
from app.db.models import Job, RediscoveryMatch, RediscoveryRun
from app.graphs.checkpointer import open_checkpointer
from app.graphs.cv_screening import build_screen_cv, job_context
from app.rediscovery.pool import RUN_KIND, SHOW_FROM, pool_ids
from app.runs.runner import graph_config, register_run_kind
from app.screening.weights import effective_weights

logger = logging.getLogger(__name__)


class RediscoveryState(TypedDict, total=False):
    """One check: the job context, the pool and each application's result."""

    run_id: int
    context: dict
    candidate_ids: list[int]
    results: Annotated[list[dict], operator.add]  # one per application


def load_pool(state: RediscoveryState) -> dict:
    """Read the job (requirements, weights, JD) and its talent pool."""
    with SessionLocal() as db:
        run = db.get(RediscoveryRun, state["run_id"])
        job = db.get(Job, run.job_id)
        candidate_ids = pool_ids(db, job)
        run.total, run.processed = len(candidate_ids), 0
        db.commit()
        context = job_context(db, job, effective_weights(job))
    return {"context": context, "candidate_ids": candidate_ids}


def send_pool(state: RediscoveryState) -> list[Send]:
    """Fan out: one screen_cv branch per past application, in parallel."""
    return [
        Send(
            "screen_cv",
            {
                "run_id": state["run_id"],
                "candidate_id": candidate_id,
                "context": state["context"],
                "progress": "rediscovery",
            },
        )
        for candidate_id in state["candidate_ids"]
    ] or [Send("collect_results", state)]


def collect_results(state: RediscoveryState) -> dict:
    """All branches are back (fan-in)."""
    return {}


def save_matches(state: RediscoveryState) -> dict:
    """Keep the applications that pass the job's mandatory requirements and
    score at least SHOW_FROM: they are the suggestions."""
    matches = [
        r
        for r in state.get("results", [])
        if r["outcome"] == "ranked" and r["overall"] >= SHOW_FROM
    ]
    with SessionLocal() as db:
        db.execute(
            delete(RediscoveryMatch).where(RediscoveryMatch.run_id == state["run_id"])
        )
        db.add_all(
            RediscoveryMatch(
                run_id=state["run_id"],
                candidate_id=r["candidate_id"],
                overall_score=r["overall"],
                dimension_scores=r["dimensions"],
                requirement_matches=r["matches"],
                summary=r["summary"],
            )
            for r in matches
        )
        run = db.get(RediscoveryRun, state["run_id"])
        run.processed = run.total
        db.commit()
    logger.info(
        "Talent pool checked: run %d, %d of %d match",
        state["run_id"],
        len(matches),
        len(state.get("results", [])),
    )
    return {}


def build_talent_rediscovery(checkpointer):
    """The talent-pool workflow, checkpointed in PostgreSQL."""
    graph = StateGraph(RediscoveryState)
    graph.add_node("load_pool", load_pool)
    graph.add_node("screen_cv", build_screen_cv())
    graph.add_node("collect_results", collect_results)
    graph.add_node("save_matches", save_matches)
    graph.add_edge(START, "load_pool")
    graph.add_conditional_edges(
        "load_pool", send_pool, ["screen_cv", "collect_results"]
    )
    graph.add_edge("screen_cv", "collect_results")
    graph.add_edge("collect_results", "save_matches")
    graph.add_edge("save_matches", END)
    return graph.compile(checkpointer=checkpointer)


def run_rediscovery(run_id: int) -> None:
    """Work function for the background runner: run (or continue) a check."""
    config = graph_config(RUN_KIND, run_id)
    config["recursion_limit"] = 50
    with open_checkpointer() as checkpointer:
        graph = build_talent_rediscovery(checkpointer)
        started = graph.get_state(config).next
        graph.invoke(None if started else {"run_id": run_id, "results": []}, config)


register_run_kind(RUN_KIND, RediscoveryRun, run_rediscovery)
