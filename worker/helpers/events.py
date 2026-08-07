import json

from redis_service import publish

STREAM_PREFIX = "stream:"


async def publish_stream(session_id: str, payload: dict) -> None:
    """Publishes a payload to the session's stream channel, which the backend
    WebSocket (`/ws/session/{session_id}`) forwards to the frontend. This is
    the single channel the frontend receives data on."""
    await publish(f"{STREAM_PREFIX}{session_id}", json.dumps(payload))
