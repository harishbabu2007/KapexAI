"""Shared HTTP, caching, and configuration support for agent tools."""

import hashlib
import json
import os
import threading
import time
from dataclasses import dataclass
from typing import Any, Mapping, Optional, Protocol

import httpx


class ToolError(RuntimeError):
    """Base exception for a tool failure."""


class ToolConfigurationError(ToolError):
    """Raised when a tool requires configuration that is not available."""


class ToolServiceError(ToolError):
    """Raised when an external service cannot satisfy a request."""


class ToolCache(Protocol):
    def get(self, key: str) -> Optional[Any]: ...

    def set(self, key: str, value: Any, ttl_seconds: int) -> None: ...


@dataclass
class _CacheEntry:
    expires_at: float
    value: Any


class InMemoryTTLCache:
    """Small development cache that can be replaced by Redis in production."""

    def __init__(self, max_entries: int = 512):
        self.max_entries = max_entries
        self._entries: dict[str, _CacheEntry] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry.expires_at <= now:
                self._entries.pop(key, None)
                return None
            return entry.value

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        with self._lock:
            if len(self._entries) >= self.max_entries:
                oldest_key = min(
                    self._entries,
                    key=lambda item: self._entries[item].expires_at,
                )
                self._entries.pop(oldest_key, None)
            self._entries[key] = _CacheEntry(
                expires_at=time.monotonic() + ttl_seconds,
                value=value,
            )


class RedisToolCache:
    """Adapter for a redis-py compatible client without forcing that dependency."""

    def __init__(self, redis_client: Any, namespace: str = "kapexai:tools"):
        self.redis_client = redis_client
        self.namespace = namespace

    def _key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def get(self, key: str) -> Optional[Any]:
        payload = self.redis_client.get(self._key(key))
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        return json.loads(payload)

    def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self.redis_client.setex(
            self._key(key),
            ttl_seconds,
            json.dumps(value, default=str, separators=(",", ":")),
        )


_cache: ToolCache = InMemoryTTLCache()
_client = httpx.Client(
    timeout=httpx.Timeout(15.0, connect=6.0),
    transport=httpx.HTTPTransport(retries=2),
    follow_redirects=True,
    headers={
        "Accept": "application/json",
        "User-Agent": "KapexAI/0.1 (+https://github.com/kapexai)",
    },
)


def configure_tool_cache(cache: ToolCache) -> None:
    """Replace the process-local cache, typically with RedisToolCache."""
    global _cache
    _cache = cache


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise ToolConfigurationError(
            f"{name} is required for this tool. Add it to the server environment."
        )
    return value


def cached_json(
    method: str,
    url: str,
    *,
    params: Optional[Mapping[str, Any]] = None,
    json_body: Optional[Any] = None,
    headers: Optional[Mapping[str, str]] = None,
    ttl_seconds: int = 900,
) -> Any:
    """Fetch JSON through the shared connection pool and TTL cache."""
    cache_key = _cache_key(method, url, params, json_body, headers)
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    response: httpx.Response | None = None
    try:
        for attempt in range(3):
            response = _client.request(
                method,
                url,
                params=params,
                json=json_body,
                headers=headers,
            )
            if response.status_code not in {429, 502, 503, 504}:
                break
            if attempt < 2:
                retry_after = response.headers.get("Retry-After")
                delay = (
                    min(float(retry_after), 3.0)
                    if retry_after and retry_after.replace(".", "", 1).isdigit()
                    else 0.5 * (2**attempt)
                )
                time.sleep(delay)
        if response is None:
            raise ToolServiceError(f"Request to {url} produced no response")
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise ToolServiceError(f"Request to {url} failed: {exc}") from exc

    _cache.set(cache_key, payload, ttl_seconds)
    return payload


def post_text(
    url: str,
    text: str,
    *,
    headers: Optional[Mapping[str, str]] = None,
    ttl_seconds: int = 3600,
) -> str:
    cache_key = _cache_key("POST", url, None, text, headers)
    cached = _cache.get(cache_key)
    if cached is not None:
        return str(cached)
    try:
        response = _client.post(url, content=text.encode("utf-8"), headers=headers)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ToolServiceError(f"Request to {url} failed: {exc}") from exc
    result = response.text
    _cache.set(cache_key, result, ttl_seconds)
    return result


def _cache_key(
    method: str,
    url: str,
    params: Optional[Mapping[str, Any]],
    body: Optional[Any],
    headers: Optional[Mapping[str, str]],
) -> str:
    material = json.dumps(
        {
            "method": method.upper(),
            "url": url,
            "params": params,
            "body": body,
            "headers": headers,
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()
