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
from starlette.websockets import WebSocketDisconnect

from db_service import connect_db, disconnect_db, db
from redis_service import connect_redis, disconnect_redis, redis

from .models.models import (
    WaitlistSignup,
    CreateChatSession,
    UserChatMessage,
    SubmitQuestionnaireAnswersRequest,
    SubmitQuestionnaireClarificationRequest,
    RenameSessionRequest,
    DeleteSessionRequest,
)
from .utils.db_utils import get_session, get_all_sessions
from .routers import auth
from .middleware.auth import get_current_user

# Marks a session's most recent message that is still being processed by the
# worker. Used so other tabs can show the in-flight message + typing indicator
# and pick up the live stream. Cleared by the worker when the job completes.
PENDING_KEY = "pending:{session_id}"
PENDING_TTL = 5 * 60  # seconds


async def mark_pending(session_id: str, content: str, msg_type: str) -> None:
    """Records the user's latest in-flight message and flags the session as
    PENDING so any tab can surface it while the worker is still replying."""
    await redis.set(
        PENDING_KEY.format(session_id=session_id),
        json.dumps({"content": content, "type": msg_type}),
        ex=PENDING_TTL,
    )
    await db.session.update(where={"id": session_id}, data={"status": "PENDING"})


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
    await mark_pending(session.id, user_data.content, "chat")

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
    await mark_pending(session.id, user_data.content, "chat")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "success", "session_id": session.id, "job_id": job["job_id"]},
    )


@app.post("/submit_questionnaire_answers")
async def submit_questionnaire_answers(user_data: SubmitQuestionnaireAnswersRequest, current_user = Depends(get_current_user)):
    """Submits structured questionnaire answers for a session. The answers are
    pushed as a job whose `user_input` carries a structured payload, so the
    worker can fold them into the business context without re-parsing free text."""
    session = await get_session(user_data.session_id)
    if not session or session.userId != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "session not found for user"},
        )

    payload = json.dumps(
        {
            "kind": "questionnaire_answers",
            "answers": [{"key": a.key, "answer": a.answer} for a in user_data.answers],
        }
    )
    job = {"job_id": str(uuid4()), "session_id": session.id, "user_input": payload}
    await redis.lpush("jobs:queue", json.dumps(job))

    content = "\n".join(
        f"{i + 1}) {a.answer or 'Skipped'}" for i, a in enumerate(user_data.answers)
    )
    await mark_pending(session.id, content, "questionnaire_answer")

    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content={"message": "success", "session_id": session.id, "job_id": job["job_id"]},
    )

@app.post("/submit_questionnaire_clarification")
async def submit_questionnaire_clarification(user_data: SubmitQuestionnaireClarificationRequest, current_user = Depends(get_current_user)):
    """Requests a plain-language explanation of specific questionnaire questions.
    Pushed as a structured job so the worker can explain without re-parsing free
    text or rejecting the request as a bad answer."""
    session = await get_session(user_data.session_id)
    if not session or session.userId != current_user.id:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"message": "session not found for user"},
        )

    payload = json.dumps(
        {"kind": "questionnaire_clarification", "keys": user_data.keys}
    )
    job = {"job_id": str(uuid4()), "session_id": session.id, "user_input": payload}
    await redis.lpush("jobs:queue", json.dumps(job))
    await mark_pending(session.id, "Asked for a simpler explanation", "chat")

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

    pending_raw = await redis.get(PENDING_KEY.format(session_id=session_id))
    pending = json.loads(pending_raw) if pending_raw else None

    return JSONResponse(
        status_code=status.HTTP_200_OK, content={"data": data, "pending": pending}
    )


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
    await redis.delete(PENDING_KEY.format(session_id=session.id))

    await db.message.delete_many(where={"sessionId": session.id})
    await db.session.delete(where={"id": session.id})

    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={"message": "success", "session_id": session.id},
    )


@app.websocket("/ws/session/{session_id}")
async def websocket_stream(websocket: WebSocket, session_id: str):
    await websocket.accept()

    # If no job is in flight for this session, nothing will be published to the
    # channel — close right away instead of holding an idle connection open.
    if not await redis.get(PENDING_KEY.format(session_id=session_id)):
        await _safe_send(websocket, {"type": "end"})
        await websocket.close()
        return

    pubsub = redis.pubsub()
    await pubsub.subscribe(f"stream:{session_id}")

    try:
        while True:
            message = await pubsub.get_message(
                ignore_subscribe_messages=True, timeout=10
            )
            if message is None:
                # Idle: if the worker has finished (pending cleared) there is
                # nothing left to stream, so signal the end and close.
                if not await redis.get(PENDING_KEY.format(session_id=session_id)):
                    await _safe_send(websocket, {"type": "end"})
                    break
                continue
            data = json.loads(message["data"])
            if not await _safe_send(websocket, data):
                # The client disconnected mid-stream — stop forwarding.
                break
            if data.get("type") == "end":
                break
    finally:
        await pubsub.unsubscribe(f"stream:{session_id}")
        await pubsub.close()
    await websocket.close()


async def _safe_send(websocket: WebSocket, data: dict) -> bool:
    """Sends a frame, returning False when the client has already gone. A tab
    that closed mid-stream (e.g. navigating away) must not crash the endpoint."""
    try:
        await websocket.send_json(data)
        return True
    except (WebSocketDisconnect, RuntimeError):
        return False
