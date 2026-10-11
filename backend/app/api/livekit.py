"""LiveKit webhook: the video server tells us who joined a call, so the
interview becomes Live with its start time (#647747).

No sign-in here: LiveKit signs every message with our shared secret, and a
message without a valid signature (or with a changed body) is refused.
"""

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.interviews import room

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/livekit", tags=["video calls"])


@router.post("/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def webhook(
    request: Request,
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str, Header()] = "",
) -> None:
    """Receive one signed event from LiveKit."""
    body = (await request.body()).decode()
    try:
        room.handle_webhook(db, body, authorization)
    except room.RoomError:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE) from None
    except Exception:  # noqa: BLE001 - a bad signature or a forged message
        logger.warning("Webhook refused: not signed by our LiveKit server")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED) from None
