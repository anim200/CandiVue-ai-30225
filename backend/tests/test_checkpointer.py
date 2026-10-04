"""A LangGraph run resumes from its last saved step after a restart (N26)."""

import operator
import uuid
from typing import Annotated, TypedDict

import pytest
from langgraph.graph import END, START, StateGraph

from app.graphs.checkpointer import open_checkpointer

pytestmark = pytest.mark.usefixtures("database_available")


class State(TypedDict):
    # operator.add: each step appends to the list instead of replacing it.
    steps: Annotated[list[str], operator.add]


def build_graph(checkpointer):
    """Two steps. It stops after step_1 to act like the app being stopped."""
    graph = StateGraph(State)
    graph.add_node("step_1", lambda state: {"steps": ["step_1"]})
    graph.add_node("step_2", lambda state: {"steps": ["step_2"]})
    graph.add_edge(START, "step_1")
    graph.add_edge("step_1", "step_2")
    graph.add_edge("step_2", END)
    return graph.compile(checkpointer=checkpointer, interrupt_after=["step_1"])


def test_graph_resumes_after_restart():
    config = {"configurable": {"thread_id": f"test-{uuid.uuid4()}"}}

    # First "app run": only step_1 runs, then the app stops.
    with open_checkpointer() as checkpointer:
        result = build_graph(checkpointer).invoke({"steps": []}, config)
        assert result["steps"] == ["step_1"]

    # Second "app run": new connections, nothing kept in memory.
    with open_checkpointer() as checkpointer:
        graph = build_graph(checkpointer)
        assert graph.get_state(config).next == ("step_2",)

        result = graph.invoke(None, config)  # None = continue, no new input

        # step_1 did not run again; only step_2 was added.
        assert result["steps"] == ["step_1", "step_2"]

        checkpointer.delete_thread(config["configurable"]["thread_id"])
