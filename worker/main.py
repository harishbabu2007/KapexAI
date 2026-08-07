import asyncio
import json
import logging
import signal
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from db_service import connect_db, disconnect_db
from redis_service import connect_redis, disconnect_redis, redis

from worker.agent import build_graph, process_job

logger = logging.getLogger(__name__)

JOB_QUEUE = "jobs:queue"


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    await connect_db()
    await connect_redis()

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)

    graph = build_graph()
    logger.info("Worker started. Listening on %s ...", JOB_QUEUE)

    while not stop.is_set():
        try:
            result = await redis.brpop(JOB_QUEUE, timeout=5)
        except Exception:
            logger.exception("Redis error while polling %s", JOB_QUEUE)
            continue

        if result is None:
            continue

        _, raw = result
        try:
            job = json.loads(raw)
            logger.info("Processing job for session %s", job.get("session_id"))
            await process_job(job, graph)
        except Exception:
            logger.exception("Failed to process job: %s", raw)

    await disconnect_redis()
    await disconnect_db()
    logger.info("Worker shut down gracefully")


if __name__ == "__main__":
    asyncio.run(main())
