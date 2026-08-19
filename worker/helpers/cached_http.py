"""Shared HTTP + TTL-caching support for worker tools.

Mirrors the pattern used by the tool scaffolding (`dummy_tools/runtime.py`) but
runs against the async `redis_service` client and through the worker's import
layout. API tokens are passed via headers only — they are never included in the
cache key, the returned payload, or error messages.
"""

import asyncio
import hashlib
import json
import logging
import os
from collections.abc import Mapping
from typing import Any

import httpx
from redis_service import redis

logger = logging.getLogger(__name__)

CACHE_PREFIX = "tool_cache"
USER_AGENT = "KapexAI/0.1 (+https://github.com/kapexai)"


class ToolError(RuntimeError):
    """Base class for tool execution failures."""


class ToolConfigurationError(ToolError):
    """A tool requires configuration (e.g. an API token) that is unavailable."""


class ToolServiceError(ToolError):
    """An external service the tool depends on failed to satisfy the request."""


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ToolConfigurationError(
            f"{name} is required for this tool. Add it to the server environment."
        )
    return value


def _cache_key(method: str, url: str, params, body: Any, data: Any) -> str:
    """Cache key from everything that identifies the request — method, URL,
    query params, JSON body and form data. Headers are deliberately excluded
    because they may carry API tokens."""
    material = json.dumps(
        {
            "method": method.upper(),
            "url": url,
            "params": params,
            "json": body,
            "data": data,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()
    return f"{CACHE_PREFIX}:{digest}"


async def cached_json(
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    data: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    ttl_seconds: int = 900,
    timeout: float = 15.0,
) -> Any:
    """Performs an HTTP request and returns the parsed JSON body, cached in
    Redis by a key that covers method/url/params/body (never headers/tokens).

    Transient failures (429/502/503/504 or transport errors) are retried a
    couple of times with a short backoff. Unrecoverable failures raise
    `ToolServiceError` so tools can degrade gracefully instead of failing the
    whole job.
    """
    key = _cache_key(method, url, params, json_body, data)
    cached = await redis.get(key)
    if cached is not None:
        try:
            return json.loads(cached)
        except (TypeError, ValueError):
            logger.warning("Dropped corrupt cache entry for %s", url)

    async with httpx.AsyncClient(
        timeout=httpx.Timeout(timeout, connect=6.0),
        follow_redirects=True,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
    ) as client:
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                response = await client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    data=data,
                    headers=headers,
                )
                last_error = None
            except httpx.HTTPError as exc:
                last_error = exc
                response = None
            if response is not None and response.status_code not in {
                429,
                502,
                503,
                504,
            }:
                break
            if attempt < 2:
                await asyncio.sleep(0.5 * (2**attempt))

        if last_error is not None:
            raise ToolServiceError(f"Request to {url} failed: {last_error}") from last_error
        try:
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise ToolServiceError(f"Request to {url} failed: {exc}") from exc

    await redis.set(key, json.dumps(payload, default=str), ex=ttl_seconds)
    return payload