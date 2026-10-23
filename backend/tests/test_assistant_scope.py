"""The Hiring Assistant's scope guardrail (app/assistant/scope.py), without
a database: which model answers count as "declined", what the off-topic turn
stores, and that both chats (job and interview room) have the rule."""

from helpers import call
from langchain_core.messages import AIMessage, ToolMessage

from app.assistant import scope
from app.assistant.prompts import ASSISTANT_PROMPT, ROOM_PROMPT
from app.assistant.tools import TOOLS
from app.graphs import hiring_assistant


def decline_call(call_id="d1", text=""):
    """A model answer that only calls decline_off_topic (maybe with text)."""
    args = {"topic": "country facts", "also_job_request": False}
    message = call(scope.TOOL_NAME, args, call_id)
    message.content = text
    return message


def test_only_a_pure_decline_counts_as_off_topic():
    mixed = AIMessage(
        content="",
        tool_calls=[
            {"name": "save_job_profile", "args": {}, "id": "a"},
            {"name": scope.TOOL_NAME, "args": {"topic": "joke"}, "id": "b"},
        ],
    )
    flagged = call(scope.TOOL_NAME, {"topic": "joke", "also_job_request": True})

    assert scope.only_declines(decline_call())
    assert not scope.only_declines(mixed)  # the job part must still run
    assert not scope.only_declines(flagged)  # the model saw a job part too
    assert not scope.only_declines(AIMessage(content="Hello! What is the job?"))
    assert not scope.only_declines(call("rag_search", {"query": "policy"}))


def test_the_decline_hides_the_models_own_text_and_keeps_history_valid():
    answer = decline_call(text="Bangladesh is a country in South Asia.")
    answer.id = "ai-1"

    quiet, result, reply = scope.decline(answer, room=False)

    assert quiet.id == "ai-1" and quiet.content == ""  # replaces the original
    assert isinstance(result, ToolMessage) and result.tool_call_id == "d1"
    assert reply.content == scope.JOB_REPLY
    assert "South Asia" not in f"{quiet.content}{result.content}{reply.content}"


def test_every_call_gets_a_result_and_the_room_has_its_own_reply():
    answer = AIMessage(
        content="",
        tool_calls=[
            {"name": scope.TOOL_NAME, "args": {"topic": "poem"}, "id": "x"},
            {"name": scope.TOOL_NAME, "args": {"topic": "news"}, "id": "y"},
        ],
        id="ai-2",
    )

    *_, first, second, reply = scope.decline(answer, room=True)

    assert {first.tool_call_id, second.tool_call_id} == {"x", "y"}
    assert reply.content == scope.ROOM_REPLY


def test_both_chats_have_the_scope_rule_and_the_tool():
    room_tools = hiring_assistant.ROOM_TOOLSET

    assert scope.decline_off_topic in TOOLS and scope.decline_off_topic in room_tools
    for prompt in (ASSISTANT_PROMPT, ROOM_PROMPT):
        assert "decline_off_topic" in prompt and "not even" in prompt
    # The job chat's answer-in-context rule and its example.
    assert '"Tell me about Bangladesh" is not' in ASSISTANT_PROMPT
