import backend.middleware.auth as auth_module
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.middleware.auth import get_current_user


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_returns_user_for_valid_token(self):
        mock_user = MagicMock(id="user-123", email="test@example.com", name="Test User")
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=mock_user)

        with (
            patch.object(auth_module, "db", mock_db),
            patch("backend.utils.jwt_utils.JWT_SECRET", "test-secret"),
        ):
            from backend.utils.jwt_utils import create_token
            token = create_token({"user_id": "user-123", "email": "test@example.com"})
            result = await get_current_user(authorization=f"Bearer {token}")

        assert result == mock_user

    @pytest.mark.asyncio
    async def test_returns_401_when_header_missing(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization=None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_401_when_header_not_bearer(self):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(authorization="Basic dGVzdDp0ZXN0")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_401_when_token_invalid(self):
        with patch("backend.utils.jwt_utils.JWT_SECRET", "test-secret"):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(authorization="Bearer invalid-token")

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_returns_401_when_user_not_found(self):
        mock_db = MagicMock()
        mock_db.user.find_unique = AsyncMock(return_value=None)

        with (
            patch.object(auth_module, "db", mock_db),
            patch("backend.utils.jwt_utils.JWT_SECRET", "test-secret"),
        ):
            from backend.utils.jwt_utils import create_token
            token = create_token({"user_id": "user-123", "email": "test@example.com"})
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(authorization=f"Bearer {token}")

        assert exc_info.value.status_code == 401