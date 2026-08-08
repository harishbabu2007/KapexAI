"""Google OAuth authentication endpoints."""

import os
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Header
from jose import jwt, JWTError

from db_service import db
from backend.models.models import GoogleTokenRequest
from backend.utils.db_utils import business_profile_is_empty, ensure_business_profile
from backend.utils.jwt_utils import create_token, decode_token

router = APIRouter(prefix="/auth", tags=["auth"])

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = os.environ.get("GOOGLE_REDIRECT_URI")

GOOGLE_CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")


async def _verify_google_id_token(credential: str) -> dict:
    """Verifies a Google sign-in ID token against Google's public keys.

    Returns the token payload if the signature, audience and issuer check
    out; raises HTTPException(401) otherwise.
    """
    async with httpx.AsyncClient() as client:
        response = await client.get(GOOGLE_CERTS_URL)
        response.raise_for_status()
        certs = response.json()

    for key in certs.get("keys", []):
        try:
            payload = jwt.decode(
                credential,
                key,
                algorithms=["RS256"],
                audience=GOOGLE_CLIENT_ID,
            )
        except JWTError:
            continue
        if payload.get("iss") not in GOOGLE_ISSUERS:
            continue
        return payload

    raise HTTPException(status_code=401, detail="Invalid Google token")


@router.get("/google")
async def google_oauth_url():
    """
    Build Google OAuth URL for user to initiate login.

    Returns:
        Dictionary with the Google OAuth authorization URL.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=500, detail="Google OAuth not configured"
        )

    scope = "openid email profile"
    url = (
        f"https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={GOOGLE_CLIENT_ID}"
        f"&redirect_uri={GOOGLE_REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={scope}"
        f"&access_type=offline"
        f"&prompt=consent"
    )
    return {"url": url}


@router.post("/google")
async def google_oauth_token(request: GoogleTokenRequest):
    """
    Exchange a Google sign-in ID token (from the popup "Sign in with Google"
    button) for a KapexAI JWT. The ID token is verified against Google's
    public keys before creating or fetching the user.

    Returns:
        Dictionary with access_token and the user's id, email and name.
    """
    if not GOOGLE_CLIENT_ID:
        raise HTTPException(
            status_code=500, detail="Google OAuth not configured"
        )

    payload = await _verify_google_id_token(request.credential)

    email = payload.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="Email not provided by Google")

    # Find or create user in database
    user = await db.user.find_unique(where={"email": email})

    if not user:
        user = await db.user.create(data={"email": email, "name": payload.get("name")})

    # Every user gets a (possibly empty) business profile row so the worker can
    # pull context from it without special-casing missing rows.
    await ensure_business_profile(user.id)
    profile_empty = await business_profile_is_empty(user.id)

    # Create JWT token
    jwt_token = create_token({"user_id": user.id, "email": user.email})

    return {
        "access_token": jwt_token,
        "user": {
            "id": user.id,
            "email": user.email,
            "name": user.name,
        },
        "profile_empty": profile_empty,
    }


@router.get("/google/callback")
async def google_oauth_callback(code: str):
    """
    Handle Google OAuth callback, exchange code for token,
    fetch user info, find or create user, and return JWT.

    Args:
        code: Authorization code from Google OAuth callback.

    Returns:
        Dictionary with access_token, email, name, and user_id.
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET or not GOOGLE_REDIRECT_URI:
        raise HTTPException(
            status_code=500, detail="Google OAuth not configured"
        )

    async with httpx.AsyncClient() as client:
        # Exchange code for access token
        token_response = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri": GOOGLE_REDIRECT_URI,
                "grant_type": "authorization_code",
            },
        )

        if token_response.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to exchange code for token"
            )

        token_data = token_response.json()
        access_token = token_data.get("access_token")

        # Fetch user info from Google
        user_response = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if user_response.status_code != 200:
            raise HTTPException(
                status_code=400, detail="Failed to fetch user info"
            )

        user_info = user_response.json()
        email = user_info.get("email")
        name = user_info.get("name")

        if not email:
            raise HTTPException(status_code=400, detail="Email not provided by Google")

    # Find or create user in database
    user = await db.user.find_unique(where={"email": email})

    if not user:
        user = await db.user.create(data={"email": email, "name": name})

    await ensure_business_profile(user.id)

    # Create JWT token
    jwt_token = create_token({"user_id": user.id, "email": user.email})

    return {
        "access_token": jwt_token,
        "email": user.email,
        "name": user.name,
        "user_id": user.id,
    }


@router.get("/me")
async def get_current_user(authorization: Optional[str] = Header(None)):
    """
    Get current authenticated user from JWT token.

    Args:
        authorization: Bearer token from Authorization header.

    Returns:
        Dictionary with user information.

    Raises:
        HTTPException: If token is missing, invalid, or user not found.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    token = authorization.split(" ")[1]
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user_id = payload.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload")

    user = await db.user.find_unique(where={"id": user_id})

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile_empty = await business_profile_is_empty(user.id)

    return {
        "user_id": user.id,
        "email": user.email,
        "name": user.name,
        "profile_empty": profile_empty,
    }