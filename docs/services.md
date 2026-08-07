# Services

## `db-service` — PostgreSQL via Prisma

**Package:** `services/database/` (published as `db-service`)

Provides a singleton Prisma async client for PostgreSQL.

| Export | Type | Description |
|---|---|---|
| `db` | `Prisma` instance | ORM client — use for queries (e.g. `await db.user.find_many()`) |
| `connect_db()` | `async` | Connect to PostgreSQL. Idempotent. |
| `disconnect_db()` | `async` | Disconnect from PostgreSQL. Idempotent. |

Usage:

```python
from db_service import db, connect_db, disconnect_db

await connect_db()
users = await db.user.find_many()
await disconnect_db()
```

Connection string via `DATABASE_URL` env var. After schema changes, run `make generate && make migrate`.

---

## `redis-service` — Redis Cloud (redis-py)

**Package:** `services/redis-service/` (published as `redis-service`)

Provides a singleton `redis.asyncio.Redis` client for Redis Cloud. All calls are async (standard TCP Redis, supports pub/sub).

| Export | Type | Description |
|---|---|---|
| `redis` | `aioredis.Redis` instance | Redis client — use for commands (e.g. `await redis.get("key")`) |
| `connect_redis()` | `async` | Verifies connectivity via `ping()`. |
| `disconnect_redis()` | `async` | Closes the connection pool. |

Usage:

```python
from redis_service import redis, connect_redis, disconnect_redis

await connect_redis()
await redis.set("key", "value")
val = await redis.get("key")
await disconnect_redis()
```

Connection string via `REDIS_URL` env var (e.g. `redis://user:pass@host:port`).

---

## Service lifecycle

### Backend (FastAPI)

Both services are connected on startup and disconnected on shutdown via FastAPI's `lifespan`:

```
startup  → await connect_db() → await connect_redis()
shutdown → await disconnect_db() → await disconnect_redis()
```

### Worker

Connects both services on startup (it uses the DB for persistence and Redis for
the job queue + pub/sub streaming):

```python
await connect_db()
await connect_redis()
# ... main loop ...
await disconnect_redis()
await disconnect_db()
```
