from db_service import db


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