"""Local time for application deadlines and interviews (APP_TIMEZONE).

Times are stored in UTC; people type and read them in local time, e.g.
"2026-10-20T17:00" means 17:00 in Dhaka.
"""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from app.core.config import get_settings


def local_zone() -> ZoneInfo:
    """The app's time zone, e.g. Asia/Dhaka."""
    return ZoneInfo(get_settings().app_timezone)


def now() -> datetime:
    """The current time (UTC)."""
    return datetime.now(UTC)


def parse_local(text: str) -> datetime:
    """Read "2026-10-20T17:00" as local time (or use its own offset, if it
    has one) and return it in UTC. A wrong format raises ValueError."""
    value = datetime.fromisoformat(text)
    if value.tzinfo is None:
        value = value.replace(tzinfo=local_zone())
    return value.astimezone(UTC)


def local_text(value: datetime) -> str:
    """A time as people read it, e.g. "Tue 20 Oct 2026, 17:00"."""
    return value.astimezone(local_zone()).strftime("%a %d %b %Y, %H:%M")
