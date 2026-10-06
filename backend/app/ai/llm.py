"""One place to call the LLM, with a timeout, retries and a clear failure (N6).

Every LangGraph calls the model through invoke_llm(). If the model still fails
after the retries, invoke_llm() raises AIServiceError, so callers handle one
error type instead of each provider's own errors.

The provider is a setting (LLM_PROVIDER / LLM_MODEL in .env), so switching
e.g. from Gemini to OpenAI needs no code change.
"""

import logging
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Wait a little longer before each retry (about 1s, 2s, 4s ... up to 10s), so
# a rate limit or short outage has time to pass. Tests turn this off.
WAIT_BETWEEN_RETRIES = True


class AIServiceError(Exception):
    """The AI model could not give an answer (timeout, outage, bad key ...)."""


@lru_cache
def get_chat_model() -> BaseChatModel:
    """Create the chat model once, from the settings."""
    settings = get_settings()
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    return init_chat_model(
        settings.llm_model,
        model_provider=settings.llm_provider,
        api_key=api_key,
        timeout=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        # Retries are done in invoke_llm(), the same way for every provider.
        max_retries=0,
    )


def invoke_llm(messages, model: Runnable | None = None):
    """Send messages to the model and return its answer.

    `model` is optional: pass a prepared model (e.g. one with tools bound for
    the Hiring Assistant) or leave it out to use the default chat model.
    Raises AIServiceError if every attempt fails.
    """
    attempts = get_settings().llm_max_retries + 1
    try:
        model = model or get_chat_model()
        retrying_model = model.with_retry(
            stop_after_attempt=attempts,
            wait_exponential_jitter=WAIT_BETWEEN_RETRIES,
            exponential_jitter_params={"initial": 1, "max": 10},
        )
        return retrying_model.invoke(messages)
    except Exception as exc:
        # Log only the error type: the message could contain prompt text.
        logger.warning(
            "LLM call failed after %d attempt(s): %s", attempts, type(exc).__name__
        )
        raise AIServiceError("The AI service is unavailable.") from exc
