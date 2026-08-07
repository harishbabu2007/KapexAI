"""JWT token utilities for authentication."""

import os
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt, JWTError


JWT_SECRET = os.environ.get("JWT_SECRET")
ALGORITHM = "HS256"
EXPIRY_DAYS = 7


def create_token(data: dict) -> str:
    """
    Create a JWT token with 7-day expiry.

    Args:
        data: Dictionary payload to encode in the token.

    Returns:
        Encoded JWT token string.
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(days=EXPIRY_DAYS)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """
    Decode and verify a JWT token.

    Args:
        token: JWT token string to decode.

    Returns:
        Decoded payload dict if valid, None if invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None