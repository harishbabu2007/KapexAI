from db_service import db
from prisma import Json


async def get_user(email: str):
    user = await db.user.find_unique(
        where={
            'email': email
        }
    )

    return user

async def get_session(session_id: str):
    session = await db.session.find_unique(
        where={
            'id': session_id
        }
    )

    return session

async def get_all_sessions(user):
    sessions = await db.session.find_many(
        where={
            'userId': user.id
        }
    )

    return sessions

async def ensure_business_profile(user_id: str):
    """Finds the user's business profile row, creating an empty one when it does
    not exist yet (e.g. accounts created before this feature shipped)."""
    profile = await db.businessprofile.find_unique(where={'userId': user_id})
    if profile is None:
        profile = await db.businessprofile.create(
            data={'userId': user_id, 'content': Json({})}
        )
    return profile

async def business_profile_is_empty(user_id: str) -> bool:
    """True when the user has not filled in anything on their business profile.
    A missing profile row (accounts created before this feature shipped) counts
    as empty without being created here — use `ensure_business_profile` lazily."""
    profile = await db.businessprofile.find_unique(where={"userId": user_id})
    if profile is None:
        return True
    content = profile.content
    if not isinstance(content, dict):
        return True
    return not any(str(value or "").strip() for value in content.values())