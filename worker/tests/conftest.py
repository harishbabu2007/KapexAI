"""Shared pytest fixtures for worker tests.

Workers tests run against the real database + Redis (per AGENTS.md), so the
connection lifecycle and the single event loop every coroutine in the suite
runs on are centralized here. Test modules must use `from conftest import
_loop, run as _run` instead of creating their own loop — the redis_service
client binds its connections to whichever loop created them, so a second loop
in the same process (e.g. a second test file) will collide with the first.
"""

import asyncio
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from db_service import connect_db, disconnect_db
from redis_service import connect_redis, disconnect_redis

_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def run(coro):
    return _loop.run_until_complete(coro)


@pytest.fixture(scope="session", autouse=True)
def services():
    run(connect_db())
    run(connect_redis())
    yield
    run(disconnect_redis())
    run(disconnect_db())
    run(_loop.shutdown_asyncgens())
    _loop.close()