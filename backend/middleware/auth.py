"""Authentication middleware - FastAPI dependency for getting current user."""

from typing import Optional

from fastapi import Header, HTTPException

from db_service import db
from backend.utils.jwt_utils import decode_token


async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    FastAPI dependency to get the currently authenticated user.

    Extracts Bearer token from Authorization header, decodes and validates JWT,
    then fetches user from database.

    Args:
        authorization: Bearer token from Authorization header.

    Returns:
        User object from database.

    Raises:
        HTTPException: 401 if token missing, invalid, expired, or user not found.
    """
    # Check if Authorization header exists and has Bearer prefix
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )

    # Extract token from "Bearer <token>"
    token = authorization.split(" ")[1]

    # Decode and verify JWT token
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )

    # Get user_id from token payload
    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload: missing user_id",
        )

    # Fetch user from database
    user = await db.user.find_unique(where={"id": user_id})
    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found",
        )

    return user