"""Google Sheets append client for user feedback.

Reliability notes
-----------------
* ``google-auth``'s ``Credentials.refresh`` is blocking (it drives urllib3), so
  it is always executed on a worker thread with :func:`asyncio.to_thread` and
  never on the event loop.
* The token request carries an **explicit socket timeout** imposed on the
  ``requests`` session. This is not redundant with the wait bound: a thread
  cannot be cancelled, so a hung token endpoint would otherwise outlive the
  request that started it.
* Only one refresh is ever in flight. Callers that time out abandon the *wait*
  (``asyncio.shield``) and leave the task running for the next caller to attach
  to, instead of releasing a lock and letting a second refresh start alongside
  the first. A cancelled future would orphan the thread and discard its token.
* The Sheets call reuses the project's existing ``httpx`` dependency with an
  explicit timeout and is issued **exactly once**. Appends are never retried
  automatically: a retry after an ambiguous failure can create a duplicate row.
* Transport/HTTP failures are classified into ``failed`` (definitely not
  written) vs ``uncertain`` (may already be in the sheet) so the caller can
  warn the user honestly. This is best-effort delivery — neither exactly-once
  nor guaranteed at-least-once.

Nothing here logs, returns or stores a token, a credential or a raw upstream
response body; only sanitized reason codes leave this module.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

import httpx
from google.auth import exceptions as google_auth_exceptions
from google.oauth2 import service_account

from backend.utils.feedback_config import FeedbackConfig

logger = logging.getLogger(__name__)

SHEETS_APPEND_URL = (
    "https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range}:append"
)
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets"

# Both network hops are bounded so a hung Google call can't pin a request open.
# TOKEN_HTTP_TIMEOUT_SECONDS bounds the token request at the socket, so its
# thread ends by itself; TOKEN_TIMEOUT_SECONDS is the looser overall bound, which
# gives that thread headroom to report the failure cleanly instead of being
# abandoned mid-flight.
TOKEN_HTTP_TIMEOUT_SECONDS = 8.0
TOKEN_TIMEOUT_SECONDS = 12.0
SHEETS_TIMEOUT_SECONDS = 15.0

# Column order of the sheet. Row 1 already contains these headers; we only ever
# append *below* the table via valueInputOption=RAW + insertDataOption=INSERT_ROWS.
FEEDBACK_SHEET_HEADERS = (
    "feedback_id",
    "created_at_utc",
    "user_id",
    "category",
    "message",
    "page_path",
    "session_id",
    "contact_allowed",
    "contact_email",
    "status",
)
# The tab must already contain these headers in row 1. We never write a header
# row, and we never compute the insert row ourselves: `INSERT_ROWS` lets Sheets
# choose where the row lands below the header.
#
# FEEDBACK_FIRST_DATA_ROW is therefore the *earliest* row a data row can occupy,
# not a guarantee. Observed in FeedbackDev: the first append landed on row 10, with
# rows 2-9 blank (no values, no formatting). We did not establish why Sheets
# chose row 10, so treat the insert position as unknown rather than deriving any
# offset from it. Nothing is lost or overwritten - later appends simply followed
# sequentially - but do not assume rows will be tightly packed.
FEEDBACK_HEADER_ROW = 1
FEEDBACK_FIRST_DATA_ROW = 2

DELIVERY_FAILED = "failed"
DELIVERY_UNCERTAIN = "uncertain"

# google-auth wraps a requests timeout (including our own socket bound) in a
# TransportError; aliased so the except clause above stays readable.
GoogleAuthTransportError = google_auth_exceptions.TransportError

_credentials: service_account.Credentials | None = None
_client: httpx.AsyncClient | None = None
# The single in-flight refresh task, or None when no refresh has been started.
# Deliberately not a lock: a thread cannot be cancelled, so "hold a lock while
# waiting" would release it on timeout while the thread kept running.
_refresh_task: asyncio.Future | None = None


class FeedbackSheetsError(Exception):
    """A Sheets append that did not succeed.

    ``delivery`` is ``"failed"`` (no row was written) or ``"uncertain"`` (the
    request may have been applied). ``reason`` is a sanitized code safe to log.
    """

    def __init__(self, reason: str, delivery: str, http_status: int | None = None):
        super().__init__(reason)
        self.reason = reason
        self.delivery = delivery
        self.http_status = http_status


def utc_now_iso() -> str:
    """Current time as a consistent, sortable UTC ISO-8601 string."""
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )


def build_feedback_row(
    *,
    feedback_id: str,
    created_at_utc: str,
    user_id: str,
    category: str,
    message: str,
    page_path: str,
    session_id: str,
    contact_allowed: bool,
    contact_email: str,
) -> list[Any]:
    """Maps a submission onto the sheet's column order.

    ``contact_allowed`` is emitted as a real JSON boolean (not a string) so RAW
    input stores an actual TRUE/FALSE cell, and the email is only ever populated
    when the user gave explicit contact permission.
    """
    return [
        feedback_id,
        created_at_utc,
        user_id,
        category,
        message,
        page_path,
        session_id,
        contact_allowed,
        contact_email,
        "new",
    ]


def _load_credentials(config: FeedbackConfig) -> service_account.Credentials:
    if config.credentials_json:
        info = json.loads(config.credentials_json)
        return service_account.Credentials.from_service_account_info(
            info, scopes=[SHEETS_SCOPE]
        )
    return service_account.Credentials.from_service_account_file(
        config.credentials_path, scopes=[SHEETS_SCOPE]
    )


def _bounded_session(timeout: float):
    """A ``requests`` session whose every call is capped at ``timeout``.

    This is not optional politeness. ``google-auth``'s transport defaults to a
    **120 second** timeout, and its IAM-endpoint path passes ``timeout=None``
    (i.e. block indefinitely), so a hung token endpoint would otherwise keep a
    thread — and its socket — alive long after the request that started it has
    already been answered. Overriding ``Session.request`` imposes our own hard
    bound and makes the thread terminate on its own, so a later caller can
    observe the failure instead of inheriting an orphan.

    ``requests`` is imported lazily so a missing/broken optional dependency
    cannot break application startup; only a feedback submission is affected.
    """
    import requests

    session = requests.Session()
    original_request = session.request

    def request_with_timeout(method, url, **kwargs):
        # Overwrite rather than default: callers (and google-auth itself) may
        # pass a larger value or None, and our bound is the one that matters.
        kwargs["timeout"] = timeout
        return original_request(method, url, **kwargs)

    session.request = request_with_timeout
    return session


def _load_and_refresh(config: FeedbackConfig) -> service_account.Credentials:
    """Blocking worker-body: read the key, then perform the token round trip.

    Runs entirely on a worker thread, including the file read, so a slow disk
    cannot stall the event loop either.
    """
    creds = _load_credentials(config)
    _refresh_credentials(creds)
    return creds


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=SHEETS_TIMEOUT_SECONDS)
    return _client


def _consume_task_exception(task: asyncio.Future) -> None:
    """Drain a failure no caller is waiting for, so asyncio does not warn.

    A refresh task can outlive every caller that awaited it (see
    :func:`_access_token`). Retrieving its exception here keeps the loop quiet
    without hiding the error, which is logged by the awaiting caller anyway.
    """
    if not task.cancelled():
        task.exception()


async def _access_token(config: FeedbackConfig) -> str:
    """Returns a valid OAuth access token, refreshing at most one at a time."""
    global _credentials, _refresh_task

    if _credentials is not None and _credentials.valid and _credentials.token:
        return _credentials.token

    # Single-flight rather than a plain lock. A lock would not be enough: a
    # thread cannot be cancelled, so a caller that gives up waiting would
    # release the lock while its refresh is still running, and the next caller
    # would start a *second* concurrent token round trip. Here there is only
    # ever one refresh task, and a caller that times out leaves it running for
    # the next one to attach to.
    if _refresh_task is None or _refresh_task.done():
        _refresh_task = asyncio.ensure_future(
            asyncio.to_thread(_load_and_refresh, config)
        )
        _refresh_task.add_done_callback(_consume_task_exception)

    task = _refresh_task
    try:
        # shield() matters: without it wait_for would cancel the future, which
        # abandons a thread that is still running and throws away its token.
        # With it, a timeout abandons only the *wait*.
        creds = await asyncio.wait_for(
            asyncio.shield(task), timeout=TOKEN_TIMEOUT_SECONDS
        )
    except (TimeoutError, GoogleAuthTransportError) as exc:
        # TimeoutError is asyncio's (3.11+ alias of asyncio.TimeoutError);
        # TransportError is google-auth wrapping a requests timeout.
        raise FeedbackSheetsError("token_timeout", DELIVERY_FAILED) from exc
    except Exception as exc:  # any credential problem is fatal here
        # Logged as a type name only — never the exception text, which can
        # contain credential material.
        logger.warning("feedback token refresh failed: %s", type(exc).__name__)
        raise FeedbackSheetsError("token_error", DELIVERY_FAILED) from exc

    if not creds.token:
        raise FeedbackSheetsError("token_missing", DELIVERY_FAILED)
    _credentials = creds
    return creds.token


def _refresh_credentials(creds: service_account.Credentials) -> None:
    from google.auth.transport.requests import Request

    # An explicit, bounded session — see _bounded_session for why this matters.
    creds.refresh(Request(session=_bounded_session(TOKEN_HTTP_TIMEOUT_SECONDS)))


def sheet_a1_range(sheet_name: str) -> str:
    """The A1 range covering the feedback columns, for use in a JSON body."""
    escaped = sheet_name.replace("'", "''")
    return f"'{escaped}'!A{len(FEEDBACK_SHEET_HEADERS)}"


def _encoded_a1_range(sheet_name: str) -> str:
    """The same range, percent-encoded for the append URL's path segment.

    The sheet name is quoted because it may contain spaces or punctuation, then
    the whole range is encoded because it travels in a URL path.
    """
    return quote(sheet_a1_range(sheet_name), safe="!:")


def _classify_http_error(status_code: int) -> FeedbackSheetsError:
    """Maps a Sheets HTTP status onto a delivery verdict.

    A 4xx is a clean rejection (nothing written). A 5xx is genuinely ambiguous —
    the request reached Google, so we cannot rule out that it was applied.
    """
    if 500 <= status_code < 600:
        return FeedbackSheetsError(
            "upstream_5xx", DELIVERY_UNCERTAIN, http_status=status_code
        )
    return FeedbackSheetsError(
        "upstream_rejected", DELIVERY_FAILED, http_status=status_code
    )


async def append_feedback_row(config: FeedbackConfig, values: list[Any]) -> dict:
    """Appends one feedback row below the table.

    Raises :class:`FeedbackSheetsError` on failure, carrying the delivery
    verdict so the endpoint can tell the user whether the row may already exist.
    """
    if len(values) != len(FEEDBACK_SHEET_HEADERS):
        raise FeedbackSheetsError("bad_row_shape", DELIVERY_FAILED)

    token = await _access_token(config)

    url = SHEETS_APPEND_URL.format(
        spreadsheet_id=config.spreadsheet_id,
        range=_encoded_a1_range(config.sheet_name),
    )
    params = {"valueInputOption": "RAW", "insertDataOption": "INSERT_ROWS"}
    body = {
        "range": sheet_a1_range(config.sheet_name),
        "majorDimension": "ROWS",
        "values": [values],
    }

    try:
        response = await _get_client().post(
            url,
            params=params,
            json=body,
            headers={"Authorization": f"Bearer {token}"},
        )
    except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
        # Never reached Google — nothing could have been written.
        raise FeedbackSheetsError("upstream_unreachable", DELIVERY_FAILED) from exc
    except (httpx.TimeoutException, httpx.RemoteProtocolError, httpx.ReadError) as exc:
        # The request was in flight when the connection broke: the write may
        # have landed, so the user must be warned before retrying.
        raise FeedbackSheetsError("upstream_timeout", DELIVERY_UNCERTAIN) from exc
    except httpx.HTTPError as exc:
        raise FeedbackSheetsError("upstream_error", DELIVERY_UNCERTAIN) from exc

    if response.status_code >= 400:
        raise _classify_http_error(response.status_code)

    try:
        payload = response.json()
    except ValueError:
        payload = {}
    return payload if isinstance(payload, dict) else {}


async def close_feedback_clients() -> None:
    """Closes the HTTP client this module owns. Safe to call when never used.

    Any in-flight refresh task is abandoned rather than cancelled: its thread
    cannot be stopped, and cancelling the future would only discard the token
    it is about to produce.
    """
    global _client, _credentials, _refresh_task
    client, _client = _client, None
    _credentials = None
    _refresh_task = None
    if client is not None and not client.is_closed:
        try:
            await client.aclose()
        except Exception as exc:
            logger.warning("feedback http client close failed: %s", type(exc).__name__)


def reset_feedback_state() -> None:
    """Drops cached credentials and any in-flight refresh task.

    Used by tests so a mocked credential never leaks between cases.
    """
    global _credentials, _refresh_task
    _credentials = None
    _refresh_task = None
