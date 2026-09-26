"""Authenticated user-feedback endpoint (backend → Google Sheets).

Design constraints this endpoint honours:

* Authentication is the existing JWT dependency; ``user_id`` and the contact
  email are derived from the authenticated user, never from the request body.
* No LLM worker involvement and no Prisma schema change — the row is appended
  straight to the spreadsheet.
* Only the ten mapped columns are ever sent. Transcripts, business profiles,
  tokens and upstream response bodies never leave this process.
* Appends are best-effort: a single attempt, no automatic retry, and an honest
  "this may already have been saved" warning when the outcome is ambiguous.
"""

import logging
import uuid

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from backend.middleware.auth import get_current_user
from backend.models.models import (
    MAX_FEEDBACK_MESSAGE_CHARS,
    FeedbackRequest,
)
from backend.utils.db_utils import get_session
from backend.utils.feedback_config import load_feedback_config, sanitize_page_path
from backend.utils.feedback_limits import (
    COOLDOWN_SECONDS,
    RateLimiterUnavailable,
    consume_feedback_quota,
)
from backend.utils.feedback_sheets import (
    DELIVERY_UNCERTAIN,
    FeedbackSheetsError,
    append_feedback_row,
    build_feedback_row,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["feedback"])

# User-facing strings are deliberately free of internal detail (upstream status
# text, IDs of internal resources, exception messages).
MSG_UNAVAILABLE = "Feedback is currently unavailable. Please try again later."
MSG_LIMITER_DOWN = (
    "Feedback is temporarily unavailable while we verify your request. "
    "Please try again shortly."
)
MSG_COOLDOWN = "You just sent feedback. Please wait a moment before sending another."
MSG_HOURLY = "You have reached the feedback limit for this hour. Please try again later."
MSG_UNCERTAIN = (
    "We could not confirm your feedback was saved. It may already be in our "
    "sheet, so please do not resend it straight away — if you do, it may appear twice."
)
MSG_DELIVERY_FAILED = (
    "We could not send your feedback just now. Your message was not saved, "
    "so please try again."
)
MSG_EMPTY_MESSAGE = "Please describe your feedback before sending."
MSG_TOO_LONG = f"Please keep your feedback under {MAX_FEEDBACK_MESSAGE_CHARS} characters."
MSG_SESSION_NOT_FOUND = "session not found for user"


def _error(
    http_status: int,
    detail: str,
    *,
    code: str,
    delivery: str = "failed",
    feedback_id: str | None = None,
    retry_after: int | None = None,
    headers: dict | None = None,
) -> JSONResponse:
    """Builds a safe error body.

    ``detail`` stays a plain string so the existing frontend API wrapper can
    surface it, while ``code``/``feedback_id``/``retry_after`` give the client
    the structured metadata it needs (reference ID, ambiguous-write warning,
    cooldown hint).
    """
    body = {"detail": detail, "code": code, "delivery": delivery}
    if feedback_id:
        body["feedback_id"] = feedback_id
    if retry_after is not None:
        body["retry_after"] = retry_after
    return JSONResponse(status_code=http_status, content=body, headers=headers or {})


@router.post("/feedback")
async def submit_feedback(
    payload: FeedbackRequest,
    current_user=Depends(get_current_user),
):
    """Records one piece of user feedback as a new row in the feedback sheet."""
    config = load_feedback_config()
    if not config.is_ready():
        # Disabled or incompletely configured: refuse cleanly. Nothing about this
        # affects auth, chat or any other route.
        logger.info(
            "feedback rejected reason=not_configured enabled=%s", config.enabled
        )
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE, MSG_UNAVAILABLE, code="feedback_disabled"
        )

    # Ordering, verified end-to-end:
    #   1. authentication  (401) — the JWT dependency, resolved by FastAPI before
    #      this function is ever called, so an unauthenticated request reaches
    #      neither Redis nor Google;
    #   2. body shape      (422) — also resolved by FastAPI, so a malformed body
    #      likewise never enters this function;
    #   3. rate limit      (Redis) — deliberately ahead of the semantic checks
    #      below, so a client cannot hammer validation or the session lookup for
    #      free. A body that fails *shape* validation costs no quota, which is
    #      fine: such a request cannot reach the write path anyway.
    try:
        decision = await consume_feedback_quota(current_user.id)
    except RateLimiterUnavailable:
        return _error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            MSG_LIMITER_DOWN,
            code="feedback_limiter_unavailable",
            retry_after=COOLDOWN_SECONDS,
        )

    if not decision.allowed:
        retry_after = max(decision.retry_after, 1)
        detail = MSG_COOLDOWN if decision.scope == "cooldown" else MSG_HOURLY
        logger.info(
            "feedback rejected reason=rate_limited scope=%s", decision.scope
        )
        return _error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            detail,
            code=f"feedback_{decision.scope}",
            retry_after=retry_after,
            headers={"Retry-After": str(retry_after)},
        )

    message = payload.message.strip()
    if not message:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, MSG_EMPTY_MESSAGE, code="feedback_empty"
        )
    if len(message) > MAX_FEEDBACK_MESSAGE_CHARS:
        return _error(
            status.HTTP_422_UNPROCESSABLE_ENTITY, MSG_TOO_LONG, code="feedback_too_long"
        )

    # Optional context only — verified for ownership, or dropped. Feedback is
    # still accepted when the user has no active conversation.
    session_id = ""
    if payload.session_id:
        session = await get_session(payload.session_id)
        if not session or session.userId != current_user.id:
            return _error(
                status.HTTP_404_NOT_FOUND,
                MSG_SESSION_NOT_FOUND,
                code="feedback_session_not_found",
            )
        session_id = session.id

    feedback_id = str(uuid.uuid4())
    contact_allowed = bool(payload.contact_allowed)
    row = build_feedback_row(
        feedback_id=feedback_id,
        created_at_utc=utc_now_iso(),
        user_id=current_user.id,
        category=payload.category,
        message=message,
        page_path=sanitize_page_path(payload.page_path),
        session_id=session_id,
        contact_allowed=contact_allowed,
        # The email is only ever stored when the user explicitly allowed contact.
        contact_email=current_user.email if contact_allowed else "",
    )

    try:
        await append_feedback_row(config, row)
    except FeedbackSheetsError as exc:
        logger.warning(
            "feedback delivery failed correlation_id=%s category=%s reason=%s delivery=%s",
            feedback_id,
            payload.category,
            exc.reason,
            exc.delivery,
        )
        if exc.delivery == DELIVERY_UNCERTAIN:
            return _error(
                status.HTTP_502_BAD_GATEWAY,
                MSG_UNCERTAIN,
                code="feedback_uncertain",
                delivery=DELIVERY_UNCERTAIN,
                feedback_id=feedback_id,
                retry_after=COOLDOWN_SECONDS,
            )
        return _error(
            status.HTTP_502_BAD_GATEWAY,
            MSG_DELIVERY_FAILED,
            code="feedback_failed",
            feedback_id=feedback_id,
        )

    logger.info(
        "feedback delivered correlation_id=%s category=%s status=new",
        feedback_id,
        payload.category,
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={
            "message": "Thanks — your feedback was recorded.",
            "feedback_id": feedback_id,
            "status": "new",
            "delivery": "delivered",
        },
    )
