"""Which AI model is used, and how much of its free daily quota is used.

Google has no API that tells how much quota an API key has left. So:
- we count our own requests per model and day, and
- when Google answers "limit reached" (HTTP 429), we save the limit and the
  time it resets, both read from Google's answer.
Google's day starts at midnight Pacific time, so our count resets then too.
The exact numbers are on Google's usage page (USAGE_URL).
"""

import logging
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.database import SessionLocal
from app.db.models import LlmModel

logger = logging.getLogger(__name__)

GOOGLE_DAY = ZoneInfo("America/Los_Angeles")  # when Google's daily quota resets
USAGE_URL = "https://ai.dev/rate-limit"
SHORT_WAIT_SECONDS = 60  # a per-minute limit: worth waiting and trying again


def google_today() -> date:
    """Today's date in Google's quota day (Pacific time)."""
    return datetime.now(GOOGLE_DAY).date()


def seconds_until_reset() -> int:
    """Seconds until Google's next quota day starts (midnight Pacific)."""
    now = datetime.now(GOOGLE_DAY)
    midnight = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return int((midnight.replace(tzinfo=GOOGLE_DAY) - now).total_seconds())


def _row(db: Session, name: str) -> LlmModel:
    """The model's row, created the first time and locked while we change it."""
    db.execute(insert(LlmModel).values(name=name).on_conflict_do_nothing())
    return db.get(LlmModel, name, with_for_update=True)


def current_model() -> str:
    """The model to use now: the interviewer's choice, else the default."""
    settings = get_settings()
    with SessionLocal() as db:
        chosen = db.scalar(select(LlmModel.name).where(LlmModel.selected))
    return chosen if chosen in settings.llm_model_list else settings.llm_model


def choose_model(db: Session, name: str) -> None:
    """Make `name` the model for every AI call (only allowed models)."""
    if name not in get_settings().llm_model_list:
        raise ValueError("This AI model is not on the allowed list.")
    db.execute(update(LlmModel).values(selected=False))
    _row(db, name).selected = True
    db.commit()
    logger.info("AI model chosen: %s", name)


def record_request(name: str) -> None:
    """Count one request to the model (the count starts again each day)."""
    with SessionLocal() as db:
        row = _row(db, name)
        today = google_today()
        if row.usage_day != today:
            row.usage_day, row.requests_today = today, 0
        row.requests_today += 1
        db.commit()


def _read_rate_limit(error: Exception) -> tuple[int | None, int | None, bool]:
    """Read Google's 429 answer: (daily limit, seconds to wait, is it daily?).
    Other providers give no details: (None, None, False)."""
    body = getattr(error.__cause__, "details", None)  # Google's JSON answer
    if not isinstance(body, dict):
        return None, None, False
    limit, wait, daily = None, None, False
    for detail in body.get("error", body).get("details", []):
        for violation in detail.get("violations", []):
            if "PerDay" in violation.get("quotaId", ""):
                daily = True
                limit = int(violation.get("quotaValue", 0)) or None
        if "retryDelay" in detail:  # e.g. "48738s"
            wait = int(float(detail["retryDelay"].rstrip("s")))
    return limit, wait, daily


def is_blocked(name: str) -> bool:
    """True while the model is known to be over its limit (no request is
    sent then: it would only fail again)."""
    with SessionLocal() as db:
        row = db.get(LlmModel, name)
        return bool(row and row.blocked_until and row.blocked_until > datetime.now(UTC))


def record_rate_limit(name: str, error: Exception) -> int:
    """Save that the model hit a limit; return the seconds until it works again."""
    limit, wait, daily = _read_rate_limit(error)
    if wait is None:
        wait = seconds_until_reset() if daily else SHORT_WAIT_SECONDS
    with SessionLocal() as db:
        row = _row(db, name)
        row.blocked_until = datetime.now(UTC) + timedelta(seconds=wait)
        if daily and limit:
            row.daily_limit = limit
            # Google counted every request today, including ones made elsewhere.
            row.usage_day = google_today()
            row.requests_today = max(row.requests_today, limit)
        db.commit()
    logger.warning("AI model %s hit a rate limit; usable in %d s", name, wait)
    return wait


def model_overview(db: Session) -> list[dict]:
    """Every allowed model with its usage today, for the model picker."""
    rows = {row.name: row for row in db.scalars(select(LlmModel))}
    chosen = current_model()
    today, now = google_today(), datetime.now(UTC)
    overview = []
    for name in get_settings().llm_model_list:
        row = rows.get(name)
        used = row.requests_today if row and row.usage_day == today else 0
        blocked = row.blocked_until if row else None
        if blocked and blocked <= now:
            blocked = None  # the limit has passed
        overview.append(
            {
                "name": name,
                "selected": name == chosen,
                "requests_today": used,
                "daily_limit": row.daily_limit if row else None,
                "blocked_until": blocked,
            }
        )
    return overview
