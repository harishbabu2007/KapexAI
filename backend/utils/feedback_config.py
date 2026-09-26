"""Environment-driven configuration for the user-feedback → Google Sheets path.

Every value is read lazily from the process environment on each call, so:

* feedback can be turned off without touching startup, auth or chat,
* a missing or partial configuration can never break unrelated routes, and
* ``POST /feedback`` always enforces the *current* configuration rather than a
  snapshot taken at import time.

Credentials are supported from a local key file (``FEEDBACK_GOOGLE_APPLICATION_
CREDENTIALS``, the usual developer setup) and from an inline JSON blob
(``FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON``, for deployments that inject secrets
from a vault). Both are backend-only — nothing here is ever exposed to the
frontend.
"""

import json
import logging
import os
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Values accepted for boolean-ish env flags.
_TRUTHY = {"1", "true", "yes", "on"}
_FALSY = {"0", "false", "no", "off", ""}

# The frontend routes the app actually serves. `page_path` is coerced to one of
# these (or dropped) so arbitrary strings never reach the spreadsheet.
KNOWN_PAGE_PATHS = frozenset({"/", "/chat", "/business-profile"})

# Bound on the raw `page_path` a client may send. Anything longer is discarded
# before the allowlist check, so a huge string is never echoed back.
MAX_PAGE_PATH_CHARS = 256


@dataclass(frozen=True)
class FeedbackConfig:
    """A snapshot of the feedback configuration for one request."""

    enabled: bool
    spreadsheet_id: str
    sheet_name: str
    credentials_path: str | None
    credentials_json: str | None

    def has_credential_source(self) -> bool:
        """True when exactly one usable credential source is configured.

        The inline JSON is parsed (never logged) so a malformed secret is
        treated as "not configured" instead of failing mid-request.
        """
        if self.credentials_json:
            try:
                parsed = json.loads(self.credentials_json)
            except (ValueError, TypeError):
                return False
            return isinstance(parsed, dict) and bool(parsed.get("client_email"))
        if self.credentials_path:
            return os.path.isfile(self.credentials_path)
        return False

    def is_ready(self) -> bool:
        """True when feedback is enabled *and* fully configured."""
        return bool(
            self.enabled
            and self.spreadsheet_id
            and self.sheet_name
            and self.has_credential_source()
        )


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or default).strip()


def feedback_enabled() -> bool:
    """Whether the feedback feature is switched on.

    Deliberately a pure env read with no client construction or network access:
    the auth endpoints call this, and authentication must never trigger a Google
    call. Unrecognised values are treated as "off" so a typo fails safe.
    """
    return _env("FEEDBACK_ENABLED").lower() in _TRUTHY


def load_feedback_config() -> FeedbackConfig:
    """Reads the current feedback configuration from the environment."""
    return FeedbackConfig(
        enabled=feedback_enabled(),
        spreadsheet_id=_env("FEEDBACK_SPREADSHEET_ID"),
        sheet_name=_env("FEEDBACK_SHEET_NAME"),
        credentials_path=_env("FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS") or None,
        credentials_json=_env("FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON") or None,
    )


def sanitize_page_path(raw: str | None) -> str:
    """Coerces a client-supplied path to a known app route.

    Query strings and fragments are dropped (they can carry identifiers), the
    value is length-bounded, and anything that is not an exact known route
    becomes an empty string rather than being stored.
    """
    if not raw:
        return ""
    candidate = raw.split("#", 1)[0].split("?", 1)[0].strip()
    if not candidate or len(candidate) > MAX_PAGE_PATH_CHARS:
        return ""
    if not candidate.startswith("/"):
        return ""
    # Trailing slashes are the only difference we forgive (`/chat/` == `/chat`).
    if len(candidate) > 1:
        candidate = candidate.rstrip("/") or "/"
    return candidate if candidate in KNOWN_PAGE_PATHS else ""
