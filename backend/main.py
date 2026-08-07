import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from fastapi import FastAPI, status, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from db_service import connect_db, disconnect_db, db
from redis_service import connect_redis, disconnect_redis, redis

from .models.models import (
    WaitlistSignup,
    CreateChatSession,
    UserChatMessage,
    RenameSessionRequest,
    DeleteSessionRequest,
)
from .utils.db_utils import get_session, get_all_sessions
from .routers import auth
from .middleware.auth import get_current_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_db()
    await connect_redis()
    yield
    await disconnect_db()
    await disconnect_redis()


app = FastAPI(title="KapexAI Backend", lifespan=lifespan)

# CORS middleware to allow requests from localhost:3000 (frontend dev server)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/waitlist")
async def join_waitlist(signup: WaitlistSignup):
    """Add email (and optional name) to waitlist. Returns success message."""
    # In a real app, you'd save to database here, e.g.:
    # await db.waitlist.create(data={"email": signup.email, "name": signup.name})
    return {"message": "Successfully joined the waitlist!", "email": signup.email}


@app.post("/create_chat_session")
async def create_chat_session(user_data: CreateChatSession, current_user = Depends(get_current_user)):
    """Creates new chat session and pushes job to redis"""
    session = await db.session.create(
        data={
            "userId": current_user.id,
            "business_idea": user_data.content,
        }
    )

    job = {"job_id": str(uuid4()), "session_id": session.id, "user_input": user_data.content}
    await redis.lpush("jobs:queue", json.dumps(job))

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "success", "session_id": session.id, "job_id": job["job_id"]},
    )


@app.post("/push_chat_message")
async def push_chat_message(user_data: UserChatMessage, current_user = Depends(get_current_user)):
    """Pushes chat message to the queue, given the session id"""
    session = await get_session(user_data.session_id)
    if not session or session.userId != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "session not found for user"},
        )

    job = {"job_id": str(uuid4()), "session_id": session.id, "user_input": user_data.content}
    await redis.lpush("jobs:queue", json.dumps(job))

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "success", "session_id": session.id, "job_id": job["job_id"]},
    )

@app.get("/get_sessions")
async def get_sessions(current_user = Depends(get_current_user)):
    sessions = await get_all_sessions(current_user)
    data = [
        {
            "id": s.id,
            "business_idea": s.business_idea,
            "status": str(s.status),
            "created_at": s.created_at.isoformat(),
        }
        for s in sessions
    ]

    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": data})


@app.get("/get_messages")
async def get_messages(session_id: str, current_user = Depends(get_current_user)):
    """Returns the message log for a session, ordered oldest → newest."""
    session = await get_session(session_id)
    if not session or session.userId != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "session not found for user"},
        )

    messages = await db.message.find_many(
        where={"sessionId": session_id},
        order={"created_at": "asc"},
    )

    data = []
    for m in messages:
        content = m.content
        if not isinstance(content, dict):
            content = {}
        data.append(
            {
                "id": m.id,
                "role": str(m.role),
                "agent": str(m.agent),
                "created_at": m.created_at.isoformat(),
                **content,
            }
        )

    return JSONResponse(status_code=status.HTTP_200_OK, content={"data": data})


@app.post("/rename_session")
async def rename_session(user_data: RenameSessionRequest, current_user = Depends(get_current_user)):
    """Renames a chat session (its `business_idea` title) for the current user."""
    session = await get_session(user_data.session_id)
    if not session or session.userId != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "session not found for user"},
        )

    name = user_data.name.strip()
    if not name:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"message": "name cannot be empty"},
        )

    updated = await db.session.update(
        where={"id": session.id},
        data={"business_idea": name},
    )

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "message": "success",
            "session_id": session.id,
            "business_idea": updated.business_idea,
        },
    )


@app.post("/delete_session")
async def delete_session(user_data: DeleteSessionRequest, current_user = Depends(get_current_user)):
    """Deletes a chat session along with all of its messages."""
    session = await get_session(user_data.session_id)
    if not session or session.userId != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "session not found for user"},
        )

    # Drop any cached graph state so it can't be resurrected by the worker.
    await redis.delete(f"langgraph_state:{session.id}")

    await db.message.delete_many(where={"sessionId": session.id})
    await db.session.delete(where={"id": session.id})

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "success", "session_id": session.id},
    )


@app.websocket("/ws/session/{session_id}")
async def websocket_stream(websocket: WebSocket, session_id: str):
    await websocket.accept()
    pubsub = redis.pubsub()
    await pubsub.subscribe(f"stream:{session_id}")

    async for message in pubsub.listen():
        if message["type"] == "message":
            data = json.loads(message["data"])
            await websocket.send_json(data)
            if data.get("type") == "end":
                break

    await pubsub.unsubscribe(f"stream:{session_id}")
    await pubsub.close()
    await websocket.close()
