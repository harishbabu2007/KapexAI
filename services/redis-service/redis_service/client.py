import os

import redis.asyncio as aioredis

redis = aioredis.from_url(
    os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
    decode_responses=True,
    socket_timeout=None,
)


async def connect_redis():
    await redis.ping()
    print("Connected to Redis")


async def disconnect_redis():
    await redis.aclose()
    print("Disconnected from Redis")


async def push_message(queue: str, message: str) -> None:
    await redis.rpush(queue, message)


async def pop_message(queue: str) -> str | None:
    return await redis.lpop(queue)


async def publish(channel: str, message: str) -> None:
    await redis.publish(channel, message)
