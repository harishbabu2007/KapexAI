"""Redis-backed rate limiting for ``POST /feedback``.

Two limits are enforced together by a single Lua script, so a submission can
never slip past one of them and a rejected submission costs exactly one round
trip:

* a 20 second cooldown between submissions (stops accidental double-sends and
  quick retry loops), and
* at most 10 submissions per hour per user.

The limiter is *fail-closed for feedback only*: if Redis is unreachable the
endpoint reports "temporarily unavailable" instead of skipping the limit, while
every unrelated route keeps working.
"""

import logging
from dataclasses import dataclass

from redis_service import redis

logger = logging.getLogger(__name__)

COOLDOWN_SECONDS = 20
HOURLY_LIMIT = 10
HOURLY_WINDOW_SECONDS = 3600

COOLDOWN_KEY = "feedback:cooldown:{user_id}"
HOURLY_KEY = "feedback:hourly:{user_id}"

# Returns {verdict, seconds_to_wait}. Verdict: 0 = cooldown, 1 = hourly cap,
# 2 = allowed. Both keys are namespaced per user id.
_RATE_LIMIT_LUA = """
local cooldown_set = redis.call('SET', KEYS[1], '1', 'NX', 'EX', ARGV[1])
if not cooldown_set then
  return {0, redis.call('TTL', KEYS[1])}
end
local count = redis.call('INCR', KEYS[2])
if count == 1 then
  redis.call('EXPIRE', KEYS[2], ARGV[2])
end
if count > tonumber(ARGV[3]) then
  return {1, redis.call('TTL', KEYS[2])}
end
return {2, 0}
"""


class RateLimiterUnavailable(Exception):
    """The limiter could not be consulted, so no quota was consumed."""


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    scope: str  # "allowed" | "cooldown" | "hourly"
    retry_after: int


async def consume_feedback_quota(user_id: str) -> RateLimitDecision:
    """Consumes one unit of the caller's feedback quota.

    Raises :class:`RateLimiterUnavailable` when Redis cannot be reached so the
    caller can refuse the submission instead of serving it unlimited.
    """
    keys = [
        COOLDOWN_KEY.format(user_id=user_id),
        HOURLY_KEY.format(user_id=user_id),
    ]
    try:
        raw = await redis.eval(
            _RATE_LIMIT_LUA,
            len(keys),
            *keys,
            COOLDOWN_SECONDS,
            HOURLY_WINDOW_SECONDS,
            HOURLY_LIMIT,
        )
    except Exception as exc:  # any Redis failure is fail-closed for this route
        logger.warning("feedback rate limiter unavailable: %s", type(exc).__name__)
        raise RateLimiterUnavailable() from exc

    verdict, retry_after = _parse_script_result(raw)
    if verdict == 0:
        return RateLimitDecision(False, "cooldown", retry_after)
    if verdict == 1:
        return RateLimitDecision(False, "hourly", retry_after)
    return RateLimitDecision(True, "allowed", 0)


def _parse_script_result(raw: object) -> tuple[int, int]:
    """Normalizes the Lua reply into (verdict, seconds_to_wait)."""
    try:
        parts = list(raw)  # type: ignore[call-overload]
        verdict = int(parts[0])
        retry_after = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError, IndexError) as exc:
        # An unrecognised reply is not a reason to serve unlimited writes.
        # Chain the cause so the underlying Redis error stays in the log.
        raise RateLimiterUnavailable() from exc
    return verdict, max(retry_after, 0)
