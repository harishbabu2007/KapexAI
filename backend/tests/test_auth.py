import backend.utils.jwt_utils as jwt_utils
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

import backend.routers.auth as auth_module
from backend.main import app
from backend.middleware.auth import get_current_user


@pytest.fixture
def client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.fixture(autouse=True)
def mock_lifespan():
    with (
        patch("backend.main.connect_db", new_callable=AsyncMock),
        patch("backend.main.disconnect_db", new_callable=AsyncMock),
        patch("backend.main.connect_redis", new_callable=AsyncMock),
        patch("backend.main.disconnect_redis", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture(autouse=True)
async def lifespan_events(mock_lifespan):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        await c.get("/health")
    yield
    app.dependency_overrides.clear()


class TestGoogleOAuthUrl:
    @pytest.mark.asyncio
    async def test_returns_google_oauth_url(self, client):
        with (
            patch("backend.routers.auth.GOOGLE_CLIENT_ID", "test-client-id"),
            patch("backend.routers.auth.GOOGLE_REDIRECT_URI", "http://localhost:8000/auth/google/callback"),
        ):
            async with client as c:
                response = await c.get("/auth/google")

        assert response.status_code == 200
        data = response.json()
        assert "url" in data
        assert "accounts.google.com/o/oauth2/v2/auth" in data["url"]
        assert "test-client-id" in data["url"]
        assert "openid" in data["url"]
        assert "email" in data["url"]
        assert "profile" in data["url"]

    @pytest.mark.asyncio
    async def test_returns_500_when_google_not_configured(self, client):
        with (
            patch("backend.routers.auth.GOOGLE_CLIENT_ID", None),
            patch("backend.routers.auth.GOOGLE_REDIRECT_URI", None),
        ):
            async with client as c:
                response = await c.get("/auth/google")

        assert response.status_code == 500


class TestGoogleOAuthToken:
    @pytest.mark.asyncio
    async def test_creates_new_user_and_returns_token(self, client):
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=None)
        new_user = MagicMock(id="u1", email="new@test.com")
        new_user.name = "New User"
        mock_db.user.create = AsyncMock(return_value=new_user)

        # The business profile helpers query their own module-level `db`.
        mock_profile = MagicMock(id="p1", content={})
        mock_utils_db = MagicMock()
        mock_utils_db.businessprofile.find_unique = AsyncMock(return_value=None)
        mock_utils_db.businessprofile.create = AsyncMock(return_value=mock_profile)

        with (
            patch.object(jwt_utils, "JWT_SECRET", "test-secret"),
            patch("backend.routers.auth.GOOGLE_CLIENT_ID", "test-client-id"),
            patch(
                "backend.routers.auth._verify_google_id_token",
                new_callable=AsyncMock,
                return_value={"email": "new@test.com", "name": "New User"},
            ),
            patch("backend.routers.auth.db", mock_db),
            patch("backend.utils.db_utils.db", mock_utils_db),
        ):
            async with client as c:
                response = await c.post("/auth/google", json={"credential": "fake-token"})

        assert response.status_code == 200
        data = response.json()
        assert data["access_token"]
        assert data["user"] == {"id": "u1", "email": "new@test.com", "name": "New User"}
        assert data["profile_empty"] is True
        mock_db.user.create.assert_awaited_once()
        mock_utils_db.businessprofile.create.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_returns_existing_user_without_creating(self, client):
        mock_db = MagicMock()
        existing_user = MagicMock(id="u9", email="existing@test.com")
        existing_user.name = "Existing"
        mock_db.user.find_unique = AsyncMock(return_value=existing_user)
        mock_db.user.create = AsyncMock()

        mock_profile = MagicMock(
            id="p9", content={"your_name": "Cafe", "location": "Pune"}
        )
        mock_utils_db = MagicMock()
        mock_utils_db.businessprofile.find_unique = AsyncMock(return_value=mock_profile)
        mock_utils_db.businessprofile.create = AsyncMock(return_value=mock_profile)

        with (
            patch.object(jwt_utils, "JWT_SECRET", "test-secret"),
            patch("backend.routers.auth.GOOGLE_CLIENT_ID", "test-client-id"),
            patch(
                "backend.routers.auth._verify_google_id_token",
                new_callable=AsyncMock,
                return_value={"email": "existing@test.com", "name": "Existing"},
            ),
            patch("backend.routers.auth.db", mock_db),
            patch("backend.utils.db_utils.db", mock_utils_db),
        ):
            async with client as c:
                response = await c.post("/auth/google", json={"credential": "fake-token"})

        assert response.status_code == 200
        assert response.json()["user"]["id"] == "u9"
        assert response.json()["profile_empty"] is False
        mock_db.user.create.assert_not_called()
        mock_utils_db.businessprofile.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejects_invalid_google_token(self, client):
        with (
            patch("backend.routers.auth.GOOGLE_CLIENT_ID", "test-client-id"),
            patch(
                "backend.routers.auth._verify_google_id_token",
                new_callable=AsyncMock,
                side_effect=HTTPException(status_code=401, detail="Invalid Google token"),
            ),
        ):
            async with client as c:
                response = await c.post("/auth/google", json={"credential": "bad-token"})

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_500_when_google_not_configured(self, client):
        with patch("backend.routers.auth.GOOGLE_CLIENT_ID", None):
            async with client as c:
                response = await c.post("/auth/google", json={"credential": "token"})

        assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_returns_422_for_missing_credential(self, client):
        with patch("backend.routers.auth.GOOGLE_CLIENT_ID", "test-client-id"):
            async with client as c:
                response = await c.post("/auth/google", json={})

        assert response.status_code == 422


class TestAuthMe:
    @pytest.mark.asyncio
    async def test_returns_user_and_profile_empty(self, client):
        user = MagicMock(id="u1", email="me@test.com")
        user.name = "Me"
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=user)
        # No business profile row → profile is empty.
        mock_utils_db = MagicMock()
        mock_utils_db.businessprofile.find_unique = AsyncMock(return_value=None)

        with (
            patch.object(jwt_utils, "JWT_SECRET", "test-secret"),
            patch("backend.routers.auth.db", mock_db),
            patch("backend.utils.db_utils.db", mock_utils_db),
        ):
            from backend.utils.jwt_utils import create_token
            token = create_token({"user_id": "u1", "email": "me@test.com"})

            async with client as c:
                response = await c.get(
                    "/auth/me", headers={"Authorization": f"Bearer {token}"}
                )

        assert response.status_code == 200
        assert response.json() == {
            "user_id": "u1",
            "email": "me@test.com",
            "name": "Me",
            "profile_empty": True,
        }

    @pytest.mark.asyncio
    async def test_returns_profile_empty_false_when_filled(self, client):
        user = MagicMock(id="u1", email="me@test.com")
        user.name = "Me"
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=user)
        mock_utils_db = MagicMock()
        mock_utils_db.businessprofile.find_unique = AsyncMock(
            return_value=MagicMock(id="p1", content={"your_name": "Cafe"})
        )

        with (
            patch.object(jwt_utils, "JWT_SECRET", "test-secret"),
            patch("backend.routers.auth.db", mock_db),
            patch("backend.utils.db_utils.db", mock_utils_db),
        ):
            from backend.utils.jwt_utils import create_token
            token = create_token({"user_id": "u1", "email": "me@test.com"})

            async with client as c:
                response = await c.get(
                    "/auth/me", headers={"Authorization": f"Bearer {token}"}
                )

        assert response.status_code == 200
        assert response.json()["profile_empty"] is False

    @pytest.mark.asyncio
    async def test_returns_401_when_token_invalid(self, client):
        async with client as c:
            response = await c.get(
                "/auth/me", headers={"Authorization": "Bearer invalid"}
            )

        assert response.status_code == 401


class TestVerifyGoogleIdToken:
    @pytest.mark.asyncio
    async def test_returns_payload_when_signature_valid(self):
        with (
            patch.object(auth_module, "GOOGLE_CLIENT_ID", "test-client-id"),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    json=MagicMock(
                        return_value={
                            "keys": [
                                {
                                    "kid": "k1",
                                    "kty": "RSA",
                                    "alg": "RS256",
                                }
                            ]
                        }
                    )
                ),
            ),
            patch.object(
                auth_module.jwt, "decode", return_value={"iss": "https://accounts.google.com"}
            ),
        ):
            payload = await auth_module._verify_google_id_token("some-token")

        assert payload["iss"] == "https://accounts.google.com"

    @pytest.mark.asyncio
    async def test_raises_when_no_key_validates(self):
        with (
            patch.object(auth_module, "GOOGLE_CLIENT_ID", "test-client-id"),
            patch(
                "httpx.AsyncClient.get",
                new_callable=AsyncMock,
                return_value=MagicMock(
                    json=MagicMock(
                        return_value={
                            "keys": [
                                {
                                    "kid": "k1",
                                    "kty": "RSA",
                                    "alg": "RS256",
                                }
                            ]
                        }
                    )
                ),
            ),
            patch.object(
                auth_module.jwt,
                "decode",
                side_effect=jwt_utils.JWTError("bad signature"),
            ),
        ):
            with pytest.raises(HTTPException) as exc:
                await auth_module._verify_google_id_token("bad-token")

        assert exc.value.status_code == 401

