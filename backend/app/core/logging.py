"""Structured (JSON) logging to stdout so Docker can collect it.

Never log personal data or secrets.
"""

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    """Formats each log line as one JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        """Turn one log record into a JSON line (time, level, logger, message)."""
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry)


def setup_logging(level: str) -> None:
    """Send all logs to the console as JSON at the given level."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level.upper(), handlers=[handler], force=True)
