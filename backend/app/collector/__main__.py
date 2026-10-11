"""Start the CV Collector: "python -m app.collector" (the cv-collector container).

Every CV_COLLECT_INTERVAL_SECONDS it collects new CVs. A failed round is
logged and tried again next time; it never stops the service.
"""

import logging
import time

from app.collector.collect import CollectorSetupError, collect_round
from app.collector.google_source import GoogleSource, GoogleSourceError, load_key
from app.core.config import get_settings
from app.core.logging import setup_logging

logger = logging.getLogger("app.collector")

NOT_SET_UP = (
    "The CV Collector is not set up yet: add GOOGLE_SERVICE_ACCOUNT_KEY and "
    "CV_RESPONSES_SHEET_ID to .env (see the README)."
)


def main() -> None:
    """Run collection rounds forever, one every few minutes."""
    settings = get_settings()
    setup_logging(settings.log_level)
    interval = settings.cv_collect_interval_seconds
    key = settings.google_service_account_key
    if not key or not settings.cv_responses_sheet_id:
        while True:  # wait quietly instead of restarting again and again
            logger.warning(NOT_SET_UP)
            time.sleep(interval)

    source = GoogleSource(
        load_key(key.get_secret_value()), settings.cv_responses_sheet_id
    )
    logger.info("CV Collector started: checking every %d s", interval)
    while True:
        try:
            result = collect_round(source)
            logger.info("CV collection round: %s", result)
        except (GoogleSourceError, CollectorSetupError) as exc:
            logger.warning("CV collection round failed: %s", exc)
        except Exception as exc:  # noqa: BLE001 - keep the service running; retry next round
            logger.warning("CV collection round failed: %s", type(exc).__name__)
        time.sleep(interval)


if __name__ == "__main__":
    main()
