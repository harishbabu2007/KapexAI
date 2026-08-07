from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from jose import jwt, JWTError

import backend.utils.jwt_utils as jwt_utils
from backend.utils.jwt_utils import create_token, decode_token


@pytest.fixture
def valid_payload():
    return {"user_id": "user-123", "email": "test@example.com"}


class TestCreateToken:
    def test_create_token_returns_string(self, valid_payload):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            token = create_token(valid_payload)
        assert isinstance(token, str)

    def test_create_token_includes_expiry(self, valid_payload):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            token = create_token(valid_payload)
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        exp = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
        assert exp > datetime.now(timezone.utc)
        assert exp < datetime.now(timezone.utc) + timedelta(days=8)

    def test_create_token_includes_original_payload(self, valid_payload):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            token = create_token(valid_payload)
        payload = jwt.decode(token, "test-secret", algorithms=["HS256"])
        assert payload["user_id"] == valid_payload["user_id"]
        assert payload["email"] == valid_payload["email"]

    def test_create_token_uses_hs256(self, valid_payload):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            token = create_token(valid_payload)
        header = jwt.get_unverified_header(token)
        assert header["alg"] == "HS256"

    def test_create_token_adds_expiry_to_copy_not_original(self, valid_payload):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            original = valid_payload.copy()
            token = create_token(valid_payload)
        assert "exp" not in valid_payload
        assert valid_payload == original


class TestDecodeToken:
    def test_decode_token_returns_payload_for_valid_token(self, valid_payload):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            token = create_token(valid_payload)
            result = decode_token(token)
        assert result is not None
        assert result["user_id"] == valid_payload["user_id"]
        assert result["email"] == valid_payload["email"]

    def test_decode_token_returns_none_for_invalid_token(self):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            result = decode_token("not.a.valid.token")
        assert result is None

    def test_decode_token_returns_none_for_expired_token(self):
        with patch.object(jwt_utils, "JWT_SECRET", "test-secret"):
            expired_payload = {"user_id": "user-123", "exp": 0}
            token = jwt.encode(expired_payload, "test-secret", algorithm="HS256")
            result = decode_token(token)
        assert result is None

    def test_decode_token_returns_none_for_wrong_secret(self, valid_payload):
        with patch.object(jwt_utils, "JWT_SECRET", "correct-secret"):
            token = create_token(valid_payload)
        with patch.object(jwt_utils, "JWT_SECRET", "wrong-secret"):
            result = decode_token(token)
        assert result is None

