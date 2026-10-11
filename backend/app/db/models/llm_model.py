"""AI models the interviewer can choose under the chat, with today's usage."""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class LlmModel(Base):
    """One AI model: is it the chosen one, and how much of Google's free
    daily quota have we used? (A row is added the first time it is used.)"""

    __tablename__ = "llm_models"

    name: Mapped[str] = mapped_column(String(100), primary_key=True)
    selected: Mapped[bool] = mapped_column(default=False)
    # Requests we sent on `usage_day` (Google's day, Pacific time).
    usage_day: Mapped[date | None] = mapped_column(Date)
    requests_today: Mapped[int] = mapped_column(default=0)
    # Learned from Google's "limit reached" answer (unknown until then).
    daily_limit: Mapped[int | None]
    blocked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
