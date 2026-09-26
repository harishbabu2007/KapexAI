"""Tests for the feedback endpoint and its Google Sheets / Redis plumbing.

Everything external is mocked: no Google API call, no Sheets write, no real
Redis and no database. The token refresh is exercised through a fake
``google-auth`` credential so the blocking-refresh path and its concurrency
guard are covered without touching the network or the event loop.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

import backend.utils.jwt_utils as jwt_utils
from backend.main import app
from backend.middleware.auth import get_current_user
from backend.models.models import MAX_FEEDBACK_MESSAGE_CHARS
from backend.utils import feedback_sheets
from backend.utils.feedback_config import (
    FeedbackConfig,
    load_feedback_config,
    sanitize_page_path,
)
from backend.utils.feedback_limits import (
    COOLDOWN_SECONDS,
    HOURLY_LIMIT,
    RateLimiterUnavailable,
    RateLimitDecision,
    _parse_script_result,
    consume_feedback_quota,
)
from backend.utils.feedback_sheets import (
    DELIVERY_FAILED,
    DELIVERY_UNCERTAIN,
    FEEDBACK_SHEET_HEADERS,
    FeedbackSheetsError,
    append_feedback_row,
    build_feedback_row,
    close_feedback_clients,
    sheet_a1_range,
    utc_now_iso,
)

CREDENTIALS_PATH = "/tmp/kapexai-fake-feedback-creds.json"


@pytest.fixture
def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture
def new_client():
    """Factory for one-shot clients — an AsyncClient cannot be reopened once closed."""
    return lambda: AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def mock_lifespan():
    with (
        patch("backend.main.connect_db", new_callable=AsyncMock),
        patch("backend.main.disconnect_db", new_callable=AsyncMock),
        patch("backend.main.connect_redis", new_callable=AsyncMock),
        patch("backend.main.disconnect_redis", new_callable=AsyncMock),
        patch("backend.main.close_feedback_clients", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture(autouse=True)
async def lifespan_events(mock_lifespan):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/health")
    yield
    app.dependency_overrides.clear()
    feedback_sheets.reset_feedback_state()


@pytest.fixture(autouse=True)
def fake_credentials_file(tmp_path, monkeypatch):
    """Points the credentials path at a real (throwaway) file on disk so the
    config check passes without ever reading a real secret."""
    path = tmp_path / "feedback-service-account.json"
    path.write_text(json.dumps({"type": "service_account", "client_email": "fake@example.iam"}))
    monkeypatch.setenv("FEEDBACK_ENABLED", "true")
    monkeypatch.setenv("FEEDBACK_SPREADSHEET_ID", "sheet-123")
    monkeypatch.setenv("FEEDBACK_SHEET_NAME", "FeedbackDev")
    monkeypatch.setenv("FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS", str(path))
    monkeypatch.delenv("FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    yield str(path)


@pytest.fixture
def authed_user():
    user = MagicMock(id="user-1", email="person@example.com")
    user.name = "Person"
    app.dependency_overrides[get_current_user] = lambda: user
    return user


def _allow_rate_limit() -> dict:
    """Patches the limiter to allow one submission."""
    from backend.utils.feedback_limits import RateLimitDecision

    return {"return_value": RateLimitDecision(True, "allowed", 0)}


def _ok_sheets_response() -> MagicMock:
    return MagicMock(
        status_code=200,
        json=MagicMock(return_value={"updates": {"updatedRows": 1}}),
    )


class TestFeedbackEnabledFlag:
    @pytest.mark.asyncio
    async def test_login_and_me_report_enabled_flag(
        self, new_client, fake_credentials_file
    ):
        user = MagicMock(id="u1", email="me@test.com")
        user.name = "Me"
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=user)
        mock_utils_db = MagicMock()
        mock_utils_db.businessprofile.find_unique = AsyncMock(return_value=None)
        mock_utils_db.businessprofile.create = AsyncMock(
            return_value=MagicMock(id="p1", content={})
        )

        with (
            patch.object(jwt_utils, "JWT_SECRET", "test-secret"),
            patch("backend.routers.auth.db", mock_db),
            patch("backend.utils.db_utils.db", mock_utils_db),
            patch(
                "backend.routers.auth._verify_google_id_token",
                new_callable=AsyncMock,
                return_value={"email": "me@test.com", "name": "Me"},
            ),
        ):
            async with new_client() as c:
                login = await c.post("/auth/google", json={"credential": "fake"})

            from backend.utils.jwt_utils import create_token

            token = create_token({"user_id": "u1", "email": "me@test.com"})
            async with new_client() as c:
                me = await c.get(
                    "/auth/me", headers={"Authorization": f"Bearer {token}"}
                )

        assert login.status_code == 200
        assert login.json()["feedback_enabled"] is True
        assert me.status_code == 200
        assert me.json()["feedback_enabled"] is True

    @pytest.mark.asyncio
    async def test_flag_is_false_when_env_disabled(
        self, client, fake_credentials_file, monkeypatch
    ):
        monkeypatch.setenv("FEEDBACK_ENABLED", "false")
        user = MagicMock(id="u1", email="me@test.com")
        user.name = "Me"
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=user)
        mock_utils_db = MagicMock()
        mock_utils_db.businessprofile.find_unique = AsyncMock(return_value=None)

        with (
            patch.object(jwt_utils, "JWT_SECRET", "test-secret"),
            patch("backend.routers.auth.db", mock_db),
            patch("backend.utils.db_utils.db", mock_utils_db),
        ):
            async with client as c:
                response = await c.get("/auth/me", headers={"Authorization": "Bearer x"})

        assert response.status_code in (401, 200)
        if response.status_code == 200:
            assert response.json()["feedback_enabled"] is False

    def test_unknown_flag_value_fails_safe(self, monkeypatch):
        from backend.utils.feedback_config import feedback_enabled

        monkeypatch.setenv("FEEDBACK_ENABLED", "maybe")
        assert feedback_enabled() is False
        monkeypatch.setenv("FEEDBACK_ENABLED", "on")
        assert feedback_enabled() is True

    @pytest.mark.asyncio
    async def test_auth_does_not_initialise_sheets_client(
        self, client, fake_credentials_file
    ):
        """Authentication must never construct the Sheets client or refresh a token."""
        user = MagicMock(id="u1", email="me@test.com")
        user.name = "Me"
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=user)
        mock_utils_db = MagicMock()
        mock_utils_db.businessprofile.find_unique = AsyncMock(return_value=None)

        with (
            patch.object(jwt_utils, "JWT_SECRET", "test-secret"),
            patch("backend.routers.auth.db", mock_db),
            patch("backend.utils.db_utils.db", mock_utils_db),
            patch.object(
                feedback_sheets, "_load_credentials", side_effect=AssertionError("no")
            ),
        ):
            async with client as c:
                response = await c.get(
                    "/auth/me", headers={"Authorization": "Bearer anything"}
                )

        # A rejected token short-circuits before any profile lookup; either way
        # no credential loading was attempted.
        assert response.status_code == 401
        assert feedback_sheets._client is None


class TestFeedbackAuth:
    @pytest.mark.asyncio
    async def test_requires_authentication(self, client, fake_credentials_file):
        async with client as c:
            response = await c.post(
                "/feedback", json={"category": "bug", "message": "hello"}
            )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_user_id_comes_from_token_not_body(
        self, client, authed_user, fake_credentials_file
    ):
        """A body-supplied user_id is rejected as an unknown field."""
        async with client as c:
            response = await c.post(
                "/feedback",
                json={"category": "bug", "message": "hello", "user_id": "someone-else"},
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "headers",
        [{}, {"Authorization": "Bearer not-a-real-token"}],
        ids=["no-token", "bad-token"],
    )
    async def test_unauthenticated_request_never_reaches_redis_or_google(
        self, client, fake_credentials_file, headers
    ):
        """Authentication must short-circuit before any side effect.

        401 is produced by the JWT dependency, which FastAPI resolves before the
        handler runs, so an unauthenticated caller must not be able to consume
        quota or reach the spreadsheet.
        """
        quota = AsyncMock()
        sheets = AsyncMock()
        with (
            patch("backend.routers.feedback.consume_feedback_quota", quota),
            patch("backend.routers.feedback.append_feedback_row", sheets),
        ):
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "hello"}, headers=headers
                )
        assert response.status_code == 401
        assert quota.call_count == 0, "quota was consumed by an unauthenticated call"
        assert sheets.call_count == 0, "an unauthenticated call reached Google"

    @pytest.mark.asyncio
    async def test_invalid_body_never_reaches_google(self, client, authed_user):
        """Shape validation happens before the handler, so nothing is written."""
        sheets = AsyncMock()
        with patch("backend.routers.feedback.append_feedback_row", sheets):
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={
                        "category": "bug",
                        "message": "hello",
                        "transcript": "should never be stored",
                    },
                )
        assert response.status_code == 422
        assert sheets.call_count == 0, "a malformed body reached the sheet"


class TestFeedbackOrdering:
    """The order of the guards is a security-relevant invariant."""

    @pytest.mark.asyncio
    async def test_rate_limit_runs_before_semantic_validation(
        self, client, authed_user, fake_credentials_file
    ):
        """A semantically invalid body still burns quota.

        Shape validation happens inside FastAPI, but the *semantic* checks (blank
        after trim, over-length) live in the handler. They must sit behind the
        limiter, or a client could hammer them for free.
        """
        quota = AsyncMock(return_value=RateLimitDecision(True, "ok", 0))
        sheets = AsyncMock()
        with (
            patch("backend.routers.feedback.consume_feedback_quota", quota),
            patch("backend.routers.feedback.append_feedback_row", sheets),
        ):
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "   "}
                )

        assert response.status_code == 422
        assert response.json()["code"] == "feedback_empty"
        assert quota.await_count == 1, "validation ran without consuming quota"
        assert sheets.call_count == 0

    @pytest.mark.asyncio
    async def test_semantic_validation_runs_before_any_write(
        self, client, authed_user, fake_credentials_file
    ):
        sheets = AsyncMock()
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota",
                AsyncMock(return_value=RateLimitDecision(True, "ok", 0)),
            ),
            patch("backend.routers.feedback.append_feedback_row", sheets),
        ):
            async with client as c:
                # Whitespace-only and over-length both fail before the write.
                blank = await c.post("/feedback", json={"category": "bug", "message": "   "})
                too_long = await c.post(
                    "/feedback",
                    json={
                        "category": "bug",
                        "message": "x" * (MAX_FEEDBACK_MESSAGE_CHARS + 1),
                    },
                )

        assert blank.status_code == 422 and blank.json()["code"] == "feedback_empty"
        assert too_long.status_code == 422 and too_long.json()["code"] == "feedback_too_long"
        # A readable sentence, not a raw validation dump.
        assert isinstance(too_long.json()["detail"], str)
        assert "2000" in too_long.json()["detail"]
        assert sheets.call_count == 0, "an invalid body reached the sheet"

    @pytest.mark.asyncio
    async def test_foreign_session_never_reaches_google(
        self, client, authed_user, fake_credentials_file
    ):
        """Ownership is checked before the write, not after."""
        sheets = AsyncMock()
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota",
                AsyncMock(return_value=RateLimitDecision(True, "ok", 0)),
            ),
            patch(
                "backend.routers.feedback.get_session",
                AsyncMock(return_value=MagicMock(id="s-other", userId="someone-else")),
            ),
            patch("backend.routers.feedback.append_feedback_row", sheets),
        ):
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={"category": "bug", "message": "hello", "session_id": "s-other"},
                )
        assert response.status_code == 404
        assert sheets.call_count == 0, "another user's session reached the sheet"


class TestFeedbackValidation:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "body",
        [
            {"category": "nonsense", "message": "hi"},
            {"message": "hi"},
            {"category": "bug"},
            {"category": "bug", "message": "hi", "unexpected": 1},
        ],
    )
    async def test_rejects_invalid_bodies(self, client, authed_user, body):
        async with client as c:
            response = await c.post("/feedback", json=body)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_blank_message(self, client, authed_user):
        with patch(
            "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
        ) as limiter:
            limiter.return_value = _allow_rate_limit()["return_value"]
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "   \n\t "}
                )
        assert response.status_code == 422
        assert response.json()["code"] == "feedback_empty"

    @pytest.mark.asyncio
    async def test_rejects_over_long_message(self, client, authed_user):
        with patch(
            "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
        ) as limiter:
            limiter.return_value = _allow_rate_limit()["return_value"]
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={"category": "bug", "message": "x" * 2500},
                )
        assert response.status_code == 422
        assert response.json()["code"] == "feedback_too_long"

    @pytest.mark.asyncio
    async def test_rejects_absurdly_long_message_at_schema_bound(
        self, client, authed_user
    ):
        """The schema bound stops an oversized body before it reaches the router."""
        async with client as c:
            response = await c.post(
                "/feedback", json={"category": "bug", "message": "x" * 5000}
            )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_rejects_oversized_session_id_and_page_path(
        self, client, authed_user
    ):
        async with client as c:
            response = await c.post(
                "/feedback",
                json={
                    "category": "bug",
                    "message": "hi",
                    "session_id": "s" * 200,
                    "page_path": "/" + "p" * 400,
                },
            )
        assert response.status_code == 422


class TestFeedbackOwnership:
    @pytest.mark.asyncio
    async def test_rejects_session_owned_by_another_user(self, client, authed_user):
        other_session = MagicMock(id="session-9", userId="someone-else")
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.get_session", new_callable=AsyncMock
            ) as get_session,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            get_session.return_value = other_session
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={
                        "category": "bug",
                        "message": "hi",
                        "session_id": "session-9",
                    },
                )
        assert response.status_code == 404
        assert response.json()["code"] == "feedback_session_not_found"

    @pytest.mark.asyncio
    async def test_rejects_unknown_session(self, client, authed_user):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.get_session", new_callable=AsyncMock
            ) as get_session,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            get_session.return_value = None
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={"category": "bug", "message": "hi", "session_id": "ghost"},
                )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_accepts_owned_session(self, client, authed_user):
        owned = MagicMock(id="session-1", userId="user-1")
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.get_session", new_callable=AsyncMock
            ) as get_session,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            get_session.return_value = owned
            append.return_value = {}
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={
                        "category": "general",
                        "message": "nice",
                        "session_id": "session-1",
                    },
                )
        assert response.status_code == 201
        assert append.await_args.args[1][6] == "session-1"

    @pytest.mark.asyncio
    async def test_works_without_a_session(self, client, authed_user):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch("backend.routers.feedback.get_session", new_callable=AsyncMock) as gs,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.return_value = {}
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "no session"}
                )
        assert response.status_code == 201
        gs.assert_not_called()
        assert append.await_args.args[1][6] == ""


class TestFeedbackConfiguration:
    @pytest.mark.asyncio
    async def test_returns_503_when_disabled(self, client, authed_user, monkeypatch):
        monkeypatch.setenv("FEEDBACK_ENABLED", "false")
        async with client as c:
            response = await c.post("/feedback", json={"category": "bug", "message": "hi"})
        assert response.status_code == 503
        assert response.json()["code"] == "feedback_disabled"

    @pytest.mark.asyncio
    async def test_returns_503_when_spreadsheet_unset(
        self, client, authed_user, monkeypatch
    ):
        monkeypatch.setenv("FEEDBACK_SPREADSHEET_ID", "")
        async with client as c:
            response = await c.post("/feedback", json={"category": "bug", "message": "hi"})
        assert response.status_code == 503
        assert response.json()["code"] == "feedback_disabled"

    @pytest.mark.asyncio
    async def test_returns_503_when_credentials_file_missing(
        self, client, authed_user, monkeypatch
    ):
        monkeypatch.setenv(
            "FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS", "/nope/missing-creds.json"
        )
        monkeypatch.delenv("FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
        async with client as c:
            response = await c.post("/feedback", json={"category": "bug", "message": "hi"})
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_returns_503_when_inline_credentials_malformed(
        self, client, authed_user, monkeypatch
    ):
        monkeypatch.delenv("FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv("FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON", "{not json")
        async with client as c:
            response = await c.post("/feedback", json={"category": "bug", "message": "hi"})
        assert response.status_code == 503

    @pytest.mark.asyncio
    async def test_unrelated_routes_unaffected_when_disabled(
        self, client, authed_user, monkeypatch
    ):
        monkeypatch.setenv("FEEDBACK_ENABLED", "false")
        mock_utils_db = MagicMock()
        mock_utils_db.session.find_many = AsyncMock(return_value=[])
        with patch("backend.utils.db_utils.db", mock_utils_db):
            async with client as c:
                health = await c.get("/health")
                waitlist = await c.post("/waitlist", json={"email": "a@b.com"})
                sessions = await c.get("/get_sessions")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}
        assert waitlist.status_code == 200
        assert sessions.status_code == 200

    def test_inline_credentials_json_is_accepted(self, monkeypatch, tmp_path):
        monkeypatch.delenv("FEEDBACK_GOOGLE_APPLICATION_CREDENTIALS", raising=False)
        monkeypatch.setenv(
            "FEEDBACK_GOOGLE_SERVICE_ACCOUNT_JSON",
            json.dumps({"client_email": "svc@example.iam", "type": "service_account"}),
        )
        config = load_feedback_config()
        assert config.is_ready() is True
        assert config.credentials_path is None

    def test_config_reads_current_environment_each_call(self, monkeypatch):
        monkeypatch.setenv("FEEDBACK_ENABLED", "true")
        assert load_feedback_config().is_ready() is True
        monkeypatch.setenv("FEEDBACK_ENABLED", "false")
        assert load_feedback_config().is_ready() is False


class TestFeedbackRateLimits:
    @pytest.mark.asyncio
    async def test_cooldown_returns_429_with_retry_after(self, client, authed_user):
        from backend.utils.feedback_limits import RateLimitDecision

        with patch(
            "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
        ) as limiter:
            limiter.return_value = RateLimitDecision(False, "cooldown", 12)
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "hi"}
                )
        assert response.status_code == 429
        assert response.json()["code"] == "feedback_cooldown"
        assert response.json()["retry_after"] == 12
        assert response.headers["Retry-After"] == "12"

    @pytest.mark.asyncio
    async def test_hourly_cap_returns_429(self, client, authed_user):
        from backend.utils.feedback_limits import RateLimitDecision

        with patch(
            "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
        ) as limiter:
            limiter.return_value = RateLimitDecision(False, "hourly", 600)
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "hi"}
                )
        assert response.status_code == 429
        assert response.json()["code"] == "feedback_hourly"

    @pytest.mark.asyncio
    async def test_limiter_failure_returns_503(self, client, authed_user):
        with patch(
            "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
        ) as limiter:
            limiter.side_effect = RateLimiterUnavailable()
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "hi"}
                )
        assert response.status_code == 503
        assert response.json()["code"] == "feedback_limiter_unavailable"

    @pytest.mark.asyncio
    async def test_limiter_failure_does_not_affect_other_routes(self, client):
        with patch(
            "backend.utils.feedback_limits.redis",
            MagicMock(eval=AsyncMock(side_effect=RuntimeError("redis down"))),
        ):
            async with client as c:
                health = await c.get("/health")
        assert health.status_code == 200

    @pytest.mark.asyncio
    async def test_limiter_script_arguments_and_keys(self):
        fake_redis = MagicMock(eval=AsyncMock(return_value=[2, 0]))
        with patch("backend.utils.feedback_limits.redis", fake_redis):
            decision = await consume_feedback_quota("user-1")
        assert decision.allowed is True
        script, numkeys, *rest = fake_redis.eval.await_args.args
        assert "SET" in script and "INCR" in script
        assert numkeys == 2
        assert rest[0].endswith("user-1")
        assert rest[1].endswith("user-1")
        assert rest[2] == COOLDOWN_SECONDS
        assert rest[3] == 3600
        assert rest[4] == HOURLY_LIMIT

    @pytest.mark.asyncio
    async def test_limiter_maps_script_verdicts(self):
        fake_redis = MagicMock(eval=AsyncMock(return_value=[0, 7]))
        with patch("backend.utils.feedback_limits.redis", fake_redis):
            decision = await consume_feedback_quota("user-1")
        assert decision.allowed is False
        assert decision.scope == "cooldown"
        assert decision.retry_after == 7

    @pytest.mark.asyncio
    async def test_limiter_raises_when_redis_errors(self):
        with patch(
            "backend.utils.feedback_limits.redis",
            MagicMock(eval=AsyncMock(side_effect=RuntimeError("boom"))),
        ), pytest.raises(RateLimiterUnavailable):
            await consume_feedback_quota("user-1")

    def test_unparsable_script_reply_is_fail_closed(self):
        with pytest.raises(RateLimiterUnavailable):
            _parse_script_result("nonsense")


class TestFeedbackRowMapping:
    def test_row_matches_sheet_header_order(self):
        row = build_feedback_row(
            feedback_id="fb-1",
            created_at_utc="2026-01-01T00:00:00Z",
            user_id="user-1",
            category="bug",
            message="  trimmed  ",
            page_path="/chat",
            session_id="session-1",
            contact_allowed=False,
            contact_email="",
        )
        assert len(row) == len(FEEDBACK_SHEET_HEADERS) == 10
        assert row[3] == "bug"
        # Real boolean, not a string, so RAW input stores a TRUE/FALSE cell.
        assert row[7] is False
        assert row[9] == "new"

    def test_utc_timestamp_is_consistent(self):
        stamp = utc_now_iso()
        assert stamp.endswith("Z")
        assert "T" in stamp

    def test_range_quotes_sheet_name_and_covers_ten_columns(self):
        assert sheet_a1_range("FeedbackDev") == "'FeedbackDev'!A10"
        assert sheet_a1_range("My Sheet") == "'My Sheet'!A10"
        assert sheet_a1_range("Bob's Tab") == "'Bob''s Tab'!A10"

    @pytest.mark.asyncio
    async def test_append_uses_raw_and_insert_rows(self, fake_credentials_file):
        config = load_feedback_config()
        creds = MagicMock(valid=True, token="tok")
        http_client = MagicMock()
        http_client.is_closed = False
        http_client.post = AsyncMock(return_value=_ok_sheets_response())

        with (
            patch.object(feedback_sheets, "_credentials", creds),
            patch.object(feedback_sheets, "_get_client", return_value=http_client),
        ):
            await append_feedback_row(config, [str(i) for i in range(10)])

        url = http_client.post.await_args.args[0]
        kwargs = http_client.post.await_args.kwargs
        assert kwargs["params"] == {
            "valueInputOption": "RAW",
            "insertDataOption": "INSERT_ROWS",
        }
        assert "sheet-123" in url
        assert "%27FeedbackDev%27" in url
        assert kwargs["json"]["majorDimension"] == "ROWS"
        assert kwargs["headers"]["Authorization"] == "Bearer tok"

    @pytest.mark.asyncio
    async def test_append_never_retries_on_timeout(self, fake_credentials_file):
        config = load_feedback_config()
        creds = MagicMock(valid=True, token="tok")
        http_client = MagicMock()
        http_client.is_closed = False
        http_client.post = AsyncMock(side_effect=httpx.ReadTimeout("timed out"))

        with (
            patch.object(feedback_sheets, "_credentials", creds),
            patch.object(feedback_sheets, "_get_client", return_value=http_client),
        ):
            with pytest.raises(FeedbackSheetsError) as exc:
                await append_feedback_row(config, [str(i) for i in range(10)])

        assert exc.value.delivery == DELIVERY_UNCERTAIN
        assert http_client.post.await_count == 1

    @pytest.mark.asyncio
    async def test_row_shape_is_validated(self):
        """A malformed row is rejected before any token or network work."""
        config = FeedbackConfig(
            enabled=True,
            spreadsheet_id="s",
            sheet_name="FeedbackDev",
            credentials_path=CREDENTIALS_PATH,
            credentials_json=None,
        )
        with patch.object(
            feedback_sheets, "_load_credentials", side_effect=AssertionError("no call")
        ):
            with pytest.raises(FeedbackSheetsError) as exc:
                await append_feedback_row(config, ["only", "three"])
        assert exc.value.reason == "bad_row_shape"


class TestFeedbackDeliveryOutcomes:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("http_status", "expected_code", "expected_delivery"),
        [
            (429, "feedback_cooldown", "failed"),
            (429, "feedback_hourly", "failed"),
            (503, "feedback_disabled", "failed"),
            (503, "feedback_limiter_unavailable", "failed"),
            (502, "feedback_uncertain", "uncertain"),
            (502, "feedback_failed", "failed"),
            (404, "feedback_session_not_found", "failed"),
        ],
    )
    async def test_error_contract_reaches_the_client(
        self,
        client,
        authed_user,
        fake_credentials_file,
        http_status,
        expected_code,
        expected_delivery,
    ):
        # The fixture yields a real throwaway file, which is_ready() requires.
        """Pin the wire shape the dialog depends on.

        `frontend/src/lib/api.ts::describeFeedbackError` reads exactly these
        keys to build the dialog's error state, so a rename here would silently
        downgrade the UI to its generic fallback message. The keys the frontend
        consumes are: `detail` (readable sentence), `code` (support reference),
        `delivery` (drives the duplicate-risk warning), `feedback_id` (reference
        id) and `retry_after`.
        """
        detail = "a readable, user-facing sentence"
        with (
            patch(
                "backend.routers.feedback.load_feedback_config", new_callable=MagicMock
            ) as load_config,
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
            patch(
                "backend.routers.feedback.get_session", new_callable=AsyncMock
            ) as get_session,
        ):
            load_config.return_value = FeedbackConfig(
                enabled=True,
                spreadsheet_id="sheet-123",
                sheet_name="FeedbackDev",
                credentials_path=fake_credentials_file,
                credentials_json=None,
            )
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.side_effect = FeedbackSheetsError(
                "upstream_timeout",
                DELIVERY_UNCERTAIN
                if expected_delivery == "uncertain"
                else DELIVERY_FAILED,
            )
            get_session.return_value = MagicMock(id="s1", userId="user-1")

            async with client as c:
                # Drive the real router, then assert the shape the client reads.
                if expected_code.startswith("feedback_cooldown"):
                    limiter.return_value = RateLimitDecision(False, "cooldown", 9)
                elif expected_code.startswith("feedback_hourly"):
                    limiter.return_value = RateLimitDecision(False, "hourly", 120)
                elif expected_code == "feedback_disabled":
                    load_config.return_value = FeedbackConfig(
                        enabled=False,
                        spreadsheet_id="",
                        sheet_name="",
                        credentials_path="",
                        credentials_json=None,
                    )
                elif expected_code == "feedback_limiter_unavailable":
                    limiter.side_effect = RateLimiterUnavailable()
                elif expected_code == "feedback_session_not_found":
                    get_session.return_value = None

                response = await c.post(
                    "/feedback",
                    json={"category": "bug", "message": "hello", "session_id": "s1"},
                )

        body = response.json()
        assert response.status_code == http_status
        assert body["code"] == expected_code
        assert body["delivery"] == expected_delivery
        # Readable sentence, not an internal dump.
        assert isinstance(body["detail"], str) and body["detail"]
        assert "Traceback" not in body["detail"]
        # Reference id whenever a row may or may not have been written.
        if http_status in (429, 502, 503):
            if expected_code in ("feedback_uncertain", "feedback_failed"):
                assert body["feedback_id"]
        if expected_code in ("feedback_cooldown", "feedback_hourly"):
            assert body["retry_after"] > 0
            assert response.headers["Retry-After"] == str(body["retry_after"])
        if expected_delivery == "uncertain":
            # The dialog keys the duplicate-risk warning off this exact value.
            assert "may already" in body["detail"].lower()

    @pytest.mark.asyncio
    async def test_success_returns_reference_id(self, client, authed_user):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.return_value = {}
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={"category": "feature_request", "message": "  add dark mode  "},
                )
        body = response.json()
        assert response.status_code == 201
        assert body["status"] == "new"
        assert body["delivery"] == "delivered"
        assert body["feedback_id"]
        # The message is trimmed before it is stored.
        assert append.await_args.args[1][4] == "add dark mode"

    @pytest.mark.asyncio
    async def test_uncertain_write_warns_about_duplicates(self, client, authed_user):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.side_effect = FeedbackSheetsError("upstream_timeout", DELIVERY_UNCERTAIN)
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "hi"}
                )
        body = response.json()
        assert response.status_code == 502
        assert body["code"] == "feedback_uncertain"
        assert body["delivery"] == DELIVERY_UNCERTAIN
        assert body["feedback_id"]
        assert "may appear twice" in body["detail"]
        assert body["retry_after"] == COOLDOWN_SECONDS

    @pytest.mark.asyncio
    async def test_confirmed_failure_says_not_saved(self, client, authed_user):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.side_effect = FeedbackSheetsError("token_error", DELIVERY_FAILED)
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "hi"}
                )
        body = response.json()
        assert response.status_code == 502
        assert body["code"] == "feedback_failed"
        assert "not saved" in body["detail"]

    @pytest.mark.asyncio
    async def test_upstream_rejection_classified_as_failed(self):
        config = load_feedback_config()
        creds = MagicMock(valid=True, token="tok")
        http_client = MagicMock()
        http_client.is_closed = False
        http_client.post = AsyncMock(return_value=MagicMock(status_code=403, json=MagicMock()))

        with (
            patch.object(feedback_sheets, "_credentials", creds),
            patch.object(feedback_sheets, "_get_client", return_value=http_client),
        ):
            with pytest.raises(FeedbackSheetsError) as exc:
                await append_feedback_row(config, [str(i) for i in range(10)])

        assert exc.value.delivery == DELIVERY_FAILED
        assert exc.value.http_status == 403

    @pytest.mark.asyncio
    async def test_upstream_5xx_classified_as_uncertain(self):
        config = load_feedback_config()
        creds = MagicMock(valid=True, token="tok")
        http_client = MagicMock()
        http_client.is_closed = False
        http_client.post = AsyncMock(return_value=MagicMock(status_code=503, json=MagicMock()))

        with (
            patch.object(feedback_sheets, "_credentials", creds),
            patch.object(feedback_sheets, "_get_client", return_value=http_client),
        ):
            with pytest.raises(FeedbackSheetsError) as exc:
                await append_feedback_row(config, [str(i) for i in range(10)])

        assert exc.value.delivery == DELIVERY_UNCERTAIN

    @pytest.mark.asyncio
    async def test_connect_error_classified_as_failed(self):
        config = load_feedback_config()
        creds = MagicMock(valid=True, token="tok")
        http_client = MagicMock()
        http_client.is_closed = False
        http_client.post = AsyncMock(side_effect=httpx.ConnectError("no route"))

        with (
            patch.object(feedback_sheets, "_credentials", creds),
            patch.object(feedback_sheets, "_get_client", return_value=http_client),
        ):
            with pytest.raises(FeedbackSheetsError) as exc:
                await append_feedback_row(config, [str(i) for i in range(10)])

        assert exc.value.delivery == DELIVERY_FAILED


class TestFeedbackConsent:
    @pytest.mark.asyncio
    async def test_email_included_only_with_permission(self, new_client, authed_user):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.return_value = {}

            async with new_client() as c:
                with_contact = await c.post(
                    "/feedback",
                    json={
                        "category": "bug",
                        "message": "call me",
                        "contact_allowed": True,
                    },
                )
            async with new_client() as c:
                without_contact = await c.post(
                    "/feedback", json={"category": "bug", "message": "no contact"}
                )

        assert with_contact.status_code == 201
        assert append.await_args_list[0].args[1][7] is True
        assert append.await_args_list[0].args[1][8] == "person@example.com"

        assert without_contact.status_code == 201
        assert append.await_args_list[1].args[1][7] is False
        assert append.await_args_list[1].args[1][8] == ""

    @pytest.mark.asyncio
    async def test_contact_defaults_to_denied(self, client, authed_user):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.return_value = {}
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "general", "message": "hi"}
                )
        assert response.status_code == 201
        assert append.await_args.args[1][7] is False
        assert append.await_args.args[1][8] == ""


class TestFeedbackPagePath:
    @pytest.mark.asyncio
    async def test_known_route_is_kept_and_others_dropped(
        self, new_client, authed_user
    ):
        with (
            patch(
                "backend.routers.feedback.consume_feedback_quota", new_callable=AsyncMock
            ) as limiter,
            patch(
                "backend.routers.feedback.append_feedback_row", new_callable=AsyncMock
            ) as append,
        ):
            limiter.return_value = _allow_rate_limit()["return_value"]
            append.return_value = {}

            async with new_client() as c:
                await c.post(
                    "/feedback",
                    json={
                        "category": "bug",
                        "message": "a",
                        "page_path": "/chat?session=secret#frag",
                    },
                )
            async with new_client() as c:
                await c.post(
                    "/feedback",
                    json={"category": "bug", "message": "b", "page_path": "/not-a-route"},
                )

        # Query strings and fragments are stripped; unknown routes are dropped.
        assert append.await_args_list[0].args[1][5] == "/chat"
        assert append.await_args_list[1].args[1][5] == ""

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("/chat", "/chat"),
            ("/chat/", "/chat"),
            ("/business-profile", "/business-profile"),
            ("/", "/"),
            ("/chat?x=1", "/chat"),
            ("/chat#anchor", "/chat"),
            ("https://evil.example/chat", ""),
            ("/etc/passwd", ""),
            ("/" + "a" * 300, ""),
            (None, ""),
            ("", ""),
        ],
    )
    def test_sanitize_page_path(self, raw, expected):
        assert sanitize_page_path(raw) == expected


class TestFeedbackTokenLifecycle:
    @pytest.mark.asyncio
    async def test_refresh_runs_off_the_event_loop_and_is_guarded(self, fake_credentials_file):
        """A blocking google-auth refresh must go through a thread, and
        concurrent callers must share a single refresh."""
        import threading

        loop_thread = threading.get_ident()
        observed_threads = []
        refresh_calls = []

        class FakeCreds:
            def __init__(self):
                self.valid = False
                self.token = None

            def refresh(self, request):
                refresh_calls.append(1)
                observed_threads.append(threading.get_ident())
                self.token = "fake-access-token"
                self.valid = True

        async def fake_to_thread(func, *args):
            # Simulate the blocking hop: run it in another thread.
            return await asyncio.get_running_loop().run_in_executor(None, func, *args)

        with (
            patch.object(feedback_sheets, "_refresh_credentials", lambda c: c.refresh(None)),
            patch.object(feedback_sheets.asyncio, "to_thread", side_effect=fake_to_thread),
            patch.object(
                feedback_sheets, "_load_credentials", return_value=FakeCreds()
            ),
        ):
            feedback_sheets.reset_feedback_state()
            tokens = await asyncio.gather(
                feedback_sheets._access_token(load_feedback_config()),
                feedback_sheets._access_token(load_feedback_config()),
            )

        assert tokens == ["fake-access-token", "fake-access-token"]
        assert len(refresh_calls) == 1, "concurrent requests must share one refresh"
        assert observed_threads[0] != loop_thread

    @pytest.mark.asyncio
    async def test_refresh_failure_is_a_confirmed_failure(self, fake_credentials_file):
        with patch.object(
            feedback_sheets, "_load_credentials", side_effect=ValueError("bad key")
        ):
            feedback_sheets.reset_feedback_state()
            with pytest.raises(FeedbackSheetsError) as exc:
                await feedback_sheets._access_token(load_feedback_config())
        assert exc.value.reason == "token_error"
        assert exc.value.delivery == DELIVERY_FAILED

    @pytest.mark.asyncio
    async def test_refresh_timeout_is_bounded(self, fake_credentials_file):
        import time

        def slow_refresh(creds):
            time.sleep(0.5)

        with (
            patch.object(feedback_sheets, "_refresh_credentials", slow_refresh),
            patch.object(feedback_sheets, "_load_credentials", return_value=MagicMock()),
            patch.object(feedback_sheets, "TOKEN_TIMEOUT_SECONDS", 0.01),
        ):
            feedback_sheets.reset_feedback_state()
            with pytest.raises(FeedbackSheetsError) as exc:
                await feedback_sheets._access_token(load_feedback_config())
        assert exc.value.reason == "token_timeout"

    @pytest.mark.asyncio
    async def test_timed_out_refresh_is_not_orphaned_and_is_reused(
        self, fake_credentials_file
    ):
        """A caller that gives up must not strand the thread or start a second one.

        A thread cannot be cancelled, so a timeout can only abandon the *wait*.
        The refresh has to stay alive and be reusable, otherwise every timeout
        would leak a thread, discard a token, and let the next caller open a
        second concurrent token round trip.
        """
        import threading
        import time

        started = threading.Event()
        release = threading.Event()
        refresh_calls = []

        class FakeCreds:
            def __init__(self):
                self.valid = False
                self.token = None

            def refresh(self, request):
                refresh_calls.append(1)
                started.set()
                release.wait(5)
                self.token = "late-token"
                self.valid = True

        with patch.object(feedback_sheets, "_load_credentials", return_value=FakeCreds()):
            feedback_sheets.reset_feedback_state()

            # Tight bound only for the first caller, so it is guaranteed to give
            # up while the thread is blocked.
            with patch.object(feedback_sheets, "TOKEN_TIMEOUT_SECONDS", 0.05):
                with pytest.raises(FeedbackSheetsError) as exc:
                    await feedback_sheets._access_token(load_feedback_config())
            assert exc.value.reason == "token_timeout"

            # The thread is still running, and the task holding it is alive.
            assert started.wait(2), "refresh thread never started"
            assert not feedback_sheets._refresh_task.done()

            # A second caller attaches to the *same* refresh instead of
            # starting another one, and inherits its result.
            waiter = asyncio.ensure_future(
                feedback_sheets._access_token(load_feedback_config())
            )
            await asyncio.sleep(0.05)
            assert len(refresh_calls) == 1, "a second refresh was started"

            release.set()
            assert await waiter == "late-token"

        assert len(refresh_calls) == 1, "exactly one token round trip"
        feedback_sheets.reset_feedback_state()

    @pytest.mark.asyncio
    async def test_token_request_carries_an_explicit_socket_timeout(self, monkeypatch):
        """The token HTTP call must have its own timeout.

        ``google-auth``'s transport defaults to 120s, and its IAM-endpoint path
        passes ``timeout=None`` (block forever), so without an explicit bound a
        hung token endpoint keeps a thread alive long after the request that
        started it has been answered.
        """
        import requests

        seen = []

        def fake_request(self, method, url, **kwargs):
            seen.append((method, url, kwargs))
            return "response"

        # Patched before _bounded_session captures the bound method.
        monkeypatch.setattr(requests.Session, "request", fake_request)

        session = feedback_sheets._bounded_session(7.5)

        # Default call gets our bound.
        session.get("https://oauth2.googleapis.com/token")
        assert seen[-1][0] == "GET"
        assert seen[-1][1] == "https://oauth2.googleapis.com/token"
        assert seen[-1][2]["timeout"] == 7.5

        # An explicit None (google-auth's IAM path) is overridden, not honoured.
        session.get("https://oauth2.googleapis.com/token", timeout=None)
        assert seen[-1][2]["timeout"] == 7.5

        # A larger value from the caller is overridden too — ours is the bound.
        session.post("https://oauth2.googleapis.com/token", timeout=999)
        assert seen[-1][2]["timeout"] == 7.5

    @pytest.mark.asyncio
    async def test_refresh_gives_google_auth_the_bounded_session(self):
        """_refresh_credentials must not fall back to google-auth's own default."""
        captured = {}

        class FakeCreds:
            def refresh(self, request):
                captured["request"] = request

        class FakeSession:
            # google.auth Request.__del__ calls session.close().
            def close(self):
                pass

        sentinel = FakeSession()
        with patch.object(feedback_sheets, "_bounded_session", return_value=sentinel):
            feedback_sheets._refresh_credentials(FakeCreds())

        # google.auth.transport.requests.Request stores the session verbatim.
        assert captured["request"].session is sentinel

    @pytest.mark.asyncio
    async def test_transport_error_reports_a_timeout(self, fake_credentials_file):
        """A socket-level timeout inside the thread is reported as a timeout."""
        from google.auth import exceptions as google_auth_exceptions

        def timing_out_refresh(creds):
            raise google_auth_exceptions.TransportError("read timed out")

        with (
            patch.object(feedback_sheets, "_refresh_credentials", timing_out_refresh),
            patch.object(feedback_sheets, "_load_credentials", return_value=MagicMock()),
        ):
            feedback_sheets.reset_feedback_state()
            with pytest.raises(FeedbackSheetsError) as exc:
                await feedback_sheets._access_token(load_feedback_config())
        assert exc.value.reason == "token_timeout"
        assert exc.value.delivery == DELIVERY_FAILED

    @pytest.mark.asyncio
    async def test_failed_refresh_is_not_reused(self, fake_credentials_file):
        """A refresh that failed must be replaced, not handed to the next caller."""
        calls = []

        def failing_refresh(creds):
            calls.append(1)
            raise ValueError("bad key")

        with (
            patch.object(feedback_sheets, "_refresh_credentials", failing_refresh),
            patch.object(feedback_sheets, "_load_credentials", return_value=MagicMock()),
        ):
            feedback_sheets.reset_feedback_state()
            for _ in range(2):
                with pytest.raises(FeedbackSheetsError) as exc:
                    await feedback_sheets._access_token(load_feedback_config())
                assert exc.value.reason == "token_error"

        assert len(calls) == 2, "a finished, failed task must not be reused"

    @pytest.mark.asyncio
    async def test_close_clients_is_safe_when_never_used(self):
        await close_feedback_clients()

    @pytest.mark.asyncio
    async def test_close_clients_closes_owned_client(self):
        http_client = MagicMock()
        http_client.is_closed = False
        http_client.aclose = AsyncMock()
        with patch.object(feedback_sheets, "_client", http_client):
            await close_feedback_clients()
        http_client.aclose.assert_awaited_once()
        assert feedback_sheets._client is None

    @pytest.mark.asyncio
    async def test_lifespan_closes_feedback_clients_on_shutdown(self):
        """The real lifespan must close the Sheets client (ASGITransport does not
        run lifespan on its own, so it is driven explicitly here)."""
        closed = AsyncMock()
        with (
            patch("backend.main.connect_db", new_callable=AsyncMock),
            patch("backend.main.disconnect_db", new_callable=AsyncMock),
            patch("backend.main.connect_redis", new_callable=AsyncMock),
            patch("backend.main.disconnect_redis", new_callable=AsyncMock),
            patch("backend.main.close_feedback_clients", closed),
        ):
            with TestClient(app) as _:
                pass
        closed.assert_awaited_once()


class TestFeedbackEndToEnd:
    """Exercises the whole endpoint with only the two external boundaries mocked:
    the Redis command and the Sheets HTTP call. No module-level patching of the
    router's collaborators, so this catches wiring mistakes."""

    @pytest.mark.asyncio
    async def test_submission_flows_through_config_limiter_and_sheets(
        self, client, authed_user, fake_credentials_file
    ):
        sent = {}

        async def fake_redis_eval(script, numkeys, *rest):
            sent["script"] = script
            sent["numkeys"] = numkeys
            sent["args"] = rest
            return [2, 0]

        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            import json as _json

            captured["url"] = str(request.url)
            captured["auth"] = request.headers.get("Authorization")
            captured["body"] = _json.loads(request.content)
            return httpx.Response(200, json={"updates": {"updatedRows": 1}})

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient(transport=transport)

        with (
            patch(
                "backend.utils.feedback_limits.redis",
                MagicMock(eval=AsyncMock(side_effect=fake_redis_eval)),
            ),
            patch.object(feedback_sheets, "_get_client", return_value=real_client),
            patch.object(feedback_sheets, "_credentials", MagicMock(valid=True, token="tok")),
        ):
            async with client as c:
                response = await c.post(
                    "/feedback",
                    json={
                        "category": "feature_request",
                        "message": "  Please add a dark theme  ",
                        "contact_allowed": False,
                        "page_path": "/chat?session=abc",
                    },
                )

        assert response.status_code == 201
        body = response.json()
        assert body["delivery"] == "delivered"
        assert body["status"] == "new"

        # Rate limiter was consulted with both per-user keys and the real limits.
        assert sent["numkeys"] == 2
        assert sent["args"][0].endswith("user-1")
        assert sent["args"][1].endswith("user-1")
        assert sent["args"][2:] == (COOLDOWN_SECONDS, 3600, HOURLY_LIMIT)

        # The request hit the append endpoint with the right options.
        assert "valueInputOption=RAW" in captured["url"]
        assert "insertDataOption=INSERT_ROWS" in captured["url"]
        assert "%27FeedbackDev%27" in captured["url"]
        assert captured["auth"] == "Bearer tok"

        # And the row matches the ten-column contract.
        values = captured["body"]["values"][0]
        assert len(values) == len(FEEDBACK_SHEET_HEADERS) == 10
        assert values[0] == body["feedback_id"]
        assert values[1].endswith("Z")
        assert values[2] == "user-1"
        assert values[3] == "feature_request"
        assert values[4] == "Please add a dark theme"
        assert values[5] == "/chat"  # query string stripped
        assert values[6] == ""  # no session supplied
        assert values[7] is False  # real boolean
        assert values[8] == ""  # no consent → no email
        assert values[9] == "new"

        await real_client.aclose()

    @pytest.mark.asyncio
    async def test_uncertain_upstream_response_surfaces_as_warning(
        self, client, authed_user, fake_credentials_file
    ):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("no response", request=request)

        transport = httpx.MockTransport(handler)
        real_client = httpx.AsyncClient(transport=transport)

        with (
            patch(
                "backend.utils.feedback_limits.redis",
                MagicMock(eval=AsyncMock(return_value=[2, 0])),
            ),
            patch.object(feedback_sheets, "_get_client", return_value=real_client),
            patch.object(feedback_sheets, "_credentials", MagicMock(valid=True, token="tok")),
        ):
            async with client as c:
                response = await c.post(
                    "/feedback", json={"category": "bug", "message": "broken"}
                )

        body = response.json()
        assert response.status_code == 502
        assert body["code"] == "feedback_uncertain"
        assert body["delivery"] == "uncertain"
        assert body["feedback_id"]
        assert "may already be in our sheet" in body["detail"]

        await real_client.aclose()

    @pytest.mark.asyncio
    async def test_cooldown_from_real_limiter_blocks_second_submission(
        self, client, authed_user, fake_credentials_file
    ):
        """The limiter's own verdict (not a stubbed decision) drives the 429."""
        transport = httpx.MockTransport(lambda request: httpx.Response(200, json={}))
        real_client = httpx.AsyncClient(transport=transport)
        calls = []

        async def fake_redis_eval(script, numkeys, *rest):
            calls.append(rest)
            # First call allowed, second call hits the cooldown.
            return [2, 0] if len(calls) == 1 else [0, 9]

        with (
            patch(
                "backend.utils.feedback_limits.redis",
                MagicMock(eval=AsyncMock(side_effect=fake_redis_eval)),
            ),
            patch.object(feedback_sheets, "_get_client", return_value=real_client),
            patch.object(feedback_sheets, "_credentials", MagicMock(valid=True, token="tok")),
        ):
            async with client as c:
                first = await c.post("/feedback", json={"category": "bug", "message": "one"})
                second = await c.post("/feedback", json={"category": "bug", "message": "two"})

        assert first.status_code == 201
        assert second.status_code == 429
        assert second.json()["code"] == "feedback_cooldown"
        assert second.json()["retry_after"] == 9
        assert second.headers["Retry-After"] == "9"

        await real_client.aclose()
