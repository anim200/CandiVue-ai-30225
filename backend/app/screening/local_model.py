"""The local AI model for the two cases the rules cannot settle (F1).

It runs in Ollama in Docker (SCREENING_MODEL, default qwen3:4b-instruct):
CV text stays on this machine and there is no quota.

1. read_years: a CV whose job dates the rules could not read. The model
   reads how many years of work experience the CV shows ("7 years of
   experience", or dates in an unusual format).
2. confirm_requirements: mandatory requirements the rules did not find,
   checked once more before the candidate is excluded (e.g. "no manual
   steps using Docker" really does show Docker).

Guard rails, so the model cannot invent anything:
- it must copy the CV line(s) it used, and a rule checks every quote is
  really in the CV;
- for years, the number must come from those lines (a stated number, the
  sum of stated durations, or no more than the years since the earliest
  year quoted);
- a quote that denies the skill or only wishes for it does not count;
- temperature 0 and a fixed seed: the same CV gets the same answer (F2).
Anything that fails a check is ignored (unknown years / requirement stays
not met), so the result is never worse than the rules alone.
"""

import logging
import re
import threading
from datetime import date
from functools import lru_cache

import ollama
from pydantic import BaseModel, Field, ValidationError

from app.ai.errors import AIServiceError
from app.core.config import get_settings
from app.screening.matching import negated

logger = logging.getLogger(__name__)

MAX_CV_CHARS = 6000  # enough for a normal CV, keeps each call a few seconds
MIN_QUOTE_CHARS = 4
SEED = 7
# Ollama on a CPU answers one request at a time. Asking one at a time here
# (several CVs are screened in parallel) keeps the timeout for the answer
# itself instead of the wait in Ollama's queue (measured in the 45-minute
# test: queued requests timed out and the screening stopped).
_one_at_a_time = threading.Lock()
NUMBER_WORDS = {  # "seven years" → 7
    word: number
    for number, word in enumerate(
        ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight"]
        + ["nine", "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen"]
        + ["sixteen", "seventeen", "eighteen", "nineteen", "twenty"]
    )
}
NUMBER = re.compile(
    r"\b(\d+(?:\.\d+)?|" + "|".join(NUMBER_WORDS) + r")\b(?!\d)", re.IGNORECASE
)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")


class YearsAnswer(BaseModel):
    """The model's answer about years of experience."""

    years: float | None = Field(
        description="Total years of professional work experience, or null if unknown"
    )
    evidence: list[str] = Field(
        description="The CV lines used, each copied word for word from the CV"
    )


class RequirementAnswer(BaseModel):
    """The model's answer about one requirement."""

    number: int = Field(description="The requirement's number in the list")
    has_it: bool
    quote: str = Field(description="The CV line that shows it, copied word for word")


class RequirementAnswers(BaseModel):
    """The model's answers about several requirements."""

    answers: list[RequirementAnswer]


YEARS_PROMPT = """You read a CV. How many years of professional work \
experience does it show?
- If the CV states it ("7 years of experience", "over five years"), use that.
- Otherwise use the jobs' dates or durations in the work history. Count \
overlapping jobs once; "present" means {today}. Do not count education.
- If the CV does not show it, answer years null.
- evidence: copy the CV lines you used, word for word.

CV:
<<<
{cv}
>>>"""

REQUIREMENTS_PROMPT = """You read a CV. For each job requirement below, \
does the CV show the candidate has it (used it at work, in a project, lists \
it as a skill, or holds it)? Answer for each number.
- has_it is false when the CV says they have not used it, or only want to \
learn it.
- quote: copy the one CV line that shows it, word for word; "" if has_it \
is false.

Requirements:
{requirements}

CV:
<<<
{cv}
>>>"""


def read_years(cv_text: str, today: date) -> tuple[float, list[str]] | None:
    """(years, evidence lines) of work experience, or None when the model
    finds none or its answer does not pass the checks."""
    prompt = YEARS_PROMPT.format(today=today.isoformat(), cv=cv_text[:MAX_CV_CHARS])
    answer = _ask(prompt, YearsAnswer)
    if answer is None or answer.years is None or not 0 < answer.years <= 60:
        return None
    quotes = [q.strip() for q in answer.evidence if len(q.strip()) >= MIN_QUOTE_CHARS]
    if not quotes or not all(in_cv(q, cv_text) for q in quotes):
        logger.info("Local model: years answer rejected (quote not in the CV)")
        return None
    if not years_supported(answer.years, quotes, today):
        logger.info("Local model: years answer rejected (number not in the quotes)")
        return None
    return round(answer.years, 1), quotes


def confirm_requirements(
    cv_text: str, requirements: list[dict]
) -> dict[str, str | None]:
    """For each requirement: the CV line that shows it, or None. One call for
    all of them."""
    lines = []
    for number, requirement in enumerate(requirements, start=1):
        line = f"{number}. {requirement['text']}"
        if requirement.get("also_counts"):
            line += f" (also counts: {', '.join(requirement['also_counts'])})"
        lines.append(line)
    prompt = REQUIREMENTS_PROMPT.format(
        requirements="\n".join(lines), cv=cv_text[:MAX_CV_CHARS]
    )
    answer = _ask(prompt, RequirementAnswers)
    given = {a.number: a for a in answer.answers} if answer else {}
    found = {}
    for number, requirement in enumerate(requirements, start=1):
        reply = given.get(number)
        found[requirement["text"]] = (
            reply.quote.strip()
            if reply and _quote_shows(reply, requirement, cv_text)
            else None
        )
    return found


def in_cv(quote: str, cv_text: str) -> bool:
    """True when the quote is really in the CV (ignoring spacing, case,
    dash and quote-mark differences)."""
    return normalised(quote) in normalised(cv_text)


def years_supported(years: float, quotes: list[str], today: date) -> bool:
    """The number must come from the quoted lines: a number stated there, the
    sum of the durations stated, or no more than the years since the earliest
    year quoted."""
    text = " ".join(quotes)
    numbers = [_number(n) for n in NUMBER.findall(YEAR.sub(" ", text))]
    if any(abs(years - n) < 0.05 for n in numbers) or (
        len(numbers) > 1 and abs(years - sum(numbers)) < 0.05
    ):
        return True
    first_year = min((int(y) for y in YEAR.findall(text)), default=None)
    return first_year is not None and years <= today.year - first_year + 1


def _quote_shows(reply: RequirementAnswer, requirement: dict, cv_text: str) -> bool:
    """The model's "yes" counts only with a real CV line that does not deny
    the requirement or only wish for it."""
    quote = reply.quote.strip()
    if not reply.has_it or len(quote) < MIN_QUOTE_CHARS or not in_cv(quote, cv_text):
        return False
    names = [requirement["text"], *requirement.get("also_counts", [])]
    return not any(negated(quote, name) for name in names)


def _ask(prompt: str, schema: type[BaseModel]) -> BaseModel | None:
    """Ask the local model for JSON that fits the schema. An answer that does
    not fit is None; a model that cannot be reached is an AIServiceError."""
    settings = get_settings()
    try:
        with _one_at_a_time:
            response = _client().chat(
                model=settings.screening_model,
                messages=[{"role": "user", "content": prompt}],
                format=schema.model_json_schema(),
                options={"temperature": 0, "seed": SEED},
            )
    except Exception as exc:
        # Only the error type: the message could contain CV text.
        logger.warning("Local screening model failed: %s", type(exc).__name__)
        raise AIServiceError(
            "The local screening model is unavailable. Please try again later."
        ) from exc
    try:
        return schema.model_validate_json(response.message.content)
    except ValidationError:
        logger.warning("Local screening model gave an answer in the wrong format")
        return None


@lru_cache
def _client() -> ollama.Client:
    """One Ollama client, from the settings."""
    settings = get_settings()
    return ollama.Client(
        host=settings.ollama_base_url, timeout=settings.screening_model_timeout_seconds
    )


def normalised(text: str) -> str:
    """Lower case, one space, plain dashes and quote marks (for comparing)."""
    for fancy, plain in (("–", "-"), ("—", "-"), ("’", "'"), ("“", '"'), ("”", '"')):
        text = text.replace(fancy, plain)
    return re.sub(r"\s+", " ", text).strip(" •·*-\"'").lower()


def _number(text: str) -> float:
    """ "7" → 7.0, "seven" → 7.0."""
    return float(NUMBER_WORDS.get(text.lower(), text))
