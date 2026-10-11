"""The one error type for AI failures (its own file, so every AI module can
use it without importing the others)."""


class AIServiceError(Exception):
    """The AI model could not give an answer (timeout, outage, bad key ...).
    The message is written by us (never prompt text), so it can be shown."""
