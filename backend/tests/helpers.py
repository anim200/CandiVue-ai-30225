"""Helpers shared by the Hiring Assistant tests: a fake LLM that plays back
prepared answers, so the real graph runs without any AI provider."""

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult


class ScriptedModel(BaseChatModel):
    """Fake chat model: returns the next prepared message on every call."""

    replies: list

    @property
    def _llm_type(self) -> str:
        """Name of this fake model type."""
        return "scripted"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """Return the next prepared reply (or raise it, to fake an outage)."""
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return ChatResult(generations=[ChatGeneration(message=reply)])

    def bind_tools(self, tools, **kwargs):
        """Tools are 'bound' by simply returning the same fake model."""
        return self


def call(name: str, args: dict, call_id: str = "c1") -> AIMessage:
    """A fake LLM answer that asks for one tool call."""
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": call_id}]
    )
