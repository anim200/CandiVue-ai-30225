"""One place to call the LLM, with a timeout, retries and a clear failure (N6).

Every LangGraph calls the model through invoke_llm(). If the model still fails
after the retries, invoke_llm() raises AIServiceError, so callers handle one
error type instead of each provider's own errors.

The provider is a setting (LLM_PROVIDER in .env), so switching e.g. from
Gemini to OpenAI needs no code change. The model is the one the interviewer
chose under the chat (app/ai/usage.py); every request is counted there so
the screen can show the free-tier quota.
"""

import logging
import time
from collections.abc import Callable
from functools import lru_cache

from langchain.chat_models import init_chat_model
from langchain_core.exceptions import ModelRateLimitError
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import Runnable

from app.ai.errors import AIServiceError
from app.ai.usage import (
    SHORT_WAIT_SECONDS,
    current_model,
    record_rate_limit,
    record_request,
)
from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Wait a little longer before each retry (1s, 2s, 4s ... up to 10s), so a
# short outage has time to pass. Tests turn this off.
WAIT_BETWEEN_RETRIES = True


@lru_cache
def get_chat_model(name: str) -> BaseChatModel:
    """Create the chat model for `name` once, from the settings."""
    settings = get_settings()
    api_key = settings.llm_api_key.get_secret_value() if settings.llm_api_key else None
    return init_chat_model(
        name,
        model_provider=settings.llm_provider,
        api_key=api_key,
        timeout=settings.llm_timeout_seconds,
        temperature=settings.llm_temperature,
        # Retries are done in invoke_llm(), the same way for every provider.
        max_retries=0,
    )


def invoke_llm(
    messages,
    prepare: Callable[[BaseChatModel], Runnable] | None = None,
    model: str | None = None,
):
    """Send messages to the chosen model and return its answer.

    `prepare` is optional: it adapts the model first, e.g. binds the Hiring
    Assistant's tools or asks for structured output. `model` is optional: a
    fixed model instead of the interviewer's choice (CV screening).
    A daily limit ("quota used up") is not retried: it would only fail again.
    Raises AIServiceError if every attempt fails.
    """
    name = model or current_model()
    attempts = get_settings().llm_max_retries + 1
    for attempt in range(1, attempts + 1):
        record_request(name)
        pause = min(2 ** (attempt - 1), 10)
        try:
            chat_model = get_chat_model(name)
            return (prepare(chat_model) if prepare else chat_model).invoke(messages)
        except ModelRateLimitError as exc:
            wait = record_rate_limit(name, exc)
            if wait > SHORT_WAIT_SECONDS or attempt == attempts:
                raise AIServiceError(
                    f"The AI model {name} has reached its usage limit. "
                    "Choose another model under the chat, or try again later."
                ) from exc
            pause = wait
        except Exception as exc:
            if attempt == attempts:
                # Log only the error type: the message could contain prompt text.
                logger.warning(
                    "LLM call failed after %d attempt(s): %s",
                    attempts,
                    type(exc).__name__,
                )
                raise AIServiceError(
                    "The AI service is unavailable. Please try again later."
                ) from exc
        if WAIT_BETWEEN_RETRIES:
            time.sleep(pause)
