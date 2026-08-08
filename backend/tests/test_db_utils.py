from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from prisma import Json

from backend.utils import db_utils


class TestEnsureBusinessProfile:
    @pytest.mark.asyncio
    async def test_returns_existing_profile(self):
        existing = MagicMock(id="p1")
        mock_db = MagicMock()
        mock_db.businessprofile.find_unique = AsyncMock(return_value=existing)
        mock_db.businessprofile.create = AsyncMock()

        with patch("backend.utils.db_utils.db", mock_db):
            result = await db_utils.ensure_business_profile("user-1")

        assert result is existing
        mock_db.businessprofile.find_unique.assert_awaited_once_with(
            where={"userId": "user-1"}
        )
        mock_db.businessprofile.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_creates_profile_when_missing(self):
        created = MagicMock(id="p2")
        mock_db = MagicMock()
        mock_db.businessprofile.find_unique = AsyncMock(return_value=None)
        mock_db.businessprofile.create = AsyncMock(return_value=created)

        with patch("backend.utils.db_utils.db", mock_db):
            result = await db_utils.ensure_business_profile("user-2")

        assert result is created
        mock_db.businessprofile.create.assert_awaited_once_with(
            data={"userId": "user-2", "content": Json({})}
        )


class TestBusinessProfileIsEmpty:
    @pytest.mark.asyncio
    async def test_true_when_no_profile_row(self):
        mock_db = MagicMock()
        mock_db.businessprofile.find_unique = AsyncMock(return_value=None)

        with patch("backend.utils.db_utils.db", mock_db):
            assert await db_utils.business_profile_is_empty("user-1") is True

    @pytest.mark.asyncio
    async def test_true_when_content_is_empty_dict(self):
        mock_db = MagicMock()
        mock_db.businessprofile.find_unique = AsyncMock(
            return_value=MagicMock(content={})
        )

        with patch("backend.utils.db_utils.db", mock_db):
            assert await db_utils.business_profile_is_empty("user-1") is True

    @pytest.mark.asyncio
    async def test_true_when_content_not_a_dict(self):
        mock_db = MagicMock()
        mock_db.businessprofile.find_unique = AsyncMock(
            return_value=MagicMock(content="not-a-dict")
        )

        with patch("backend.utils.db_utils.db", mock_db):
            assert await db_utils.business_profile_is_empty("user-1") is True

    @pytest.mark.asyncio
    async def test_true_when_all_values_blank_or_whitespace(self):
        mock_db = MagicMock()
        mock_db.businessprofile.find_unique = AsyncMock(
            return_value=MagicMock(
                content={"your_name": "", "location": "   ", "industry": None}
            )
        )

        with patch("backend.utils.db_utils.db", mock_db):
            assert await db_utils.business_profile_is_empty("user-1") is True

    @pytest.mark.asyncio
    async def test_false_when_at_least_one_value_filled(self):
        mock_db = MagicMock()
        mock_db.businessprofile.find_unique = AsyncMock(
            return_value=MagicMock(
                content={"your_name": "", "location": "Pune", "industry": ""}
            )
        )

        with patch("backend.utils.db_utils.db", mock_db):
            assert await db_utils.business_profile_is_empty("user-1") is False
