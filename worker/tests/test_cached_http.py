"""Unit tests for `worker/helpers/cached_http.py` — the TTL-cached HTTP layer
used by the legal tools.

Covers: `require_env` credential checks, cache-key stability (no headers in the
key), caching + TTL behaviour, retry/backoff on transient failures, and the
typed `ToolServiceError` mapping for unrecoverable/HTTP errors. The HTTP layer
is faked so no real network calls are made; the cache lives in the shared
Redis client (session fixture from `conftest.py`), and each test cleans up its
own key.
"""

import json

import httpx
import pytest
from conftest import run as _run
from redis_service import redis

# conftest already loaded the root `.env` and the shared `redis_service`
# client, so importing cached_http is safe (real REDIS_URL, not localhost).
from worker.helpers.cached_http import (
    ToolConfigurationError,
    ToolServiceError,
    _cache_key,
    cached_json,
    require_env,
)

_METHOD = "GET"
_URL = "https://api.stub.example/v1/test"
_PARAMS = {"q": "south indian restaurant"}
_PAYLOAD = {"results": [{"title": "FSSAI", "authority": "FSSAI"}]}
_HEADERS = {"Authorization": "Bearer secret-token"}


class FakeResponse:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._json_body = body if isinstance(body, (dict, list)) else None
        self._text = body if isinstance(body, str) else json.dumps(body)

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                f"HTTP {self.status_code}",
                request=httpx.Request("GET", _URL),
                response=self,
            )

    def json(self):
        if self._json_body is not None:
            return self._json_body
        raise ValueError(f"Expected JSON, got: {self._text!r}")


class FakeClient:
    """Async context manager standing in for `httpx.AsyncClient`. Responses are
    consumed in order; an `Exception` entry is raised instead of returned."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def request(self, method, url, **kwargs):
        self.calls.append((method.upper(), url, kwargs))
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _delete_cache() -> None:
    key = _cache_key(_METHOD, _URL, _PARAMS, None, None)
    _run(redis.delete(key))


@pytest.fixture(autouse=True)
def _clean_cache():
    _delete_cache()
    yield
    _delete_cache()


@pytest.fixture
def fake_http(monkeypatch):
    def maker(responses):
        client = FakeClient(responses)
        monkeypatch.setattr("worker.helpers.cached_http.httpx.AsyncClient", lambda **_: client)
        return client

    return maker


# ── require_env ──────────────────────────────────────────────


def test_require_env_returns_value(monkeypatch):
    monkeypatch.setenv("KAPEX_TEST_TOKEN", "abc123")
    assert require_env("KAPEX_TEST_TOKEN") == "abc123"


def test_require_env_missing_raises(monkeypatch):
    monkeypatch.delenv("KAPEX_TEST_TOKEN", raising=False)
    with pytest.raises(ToolConfigurationError, match="KAPEX_TEST_TOKEN"):
        require_env("KAPEX_TEST_TOKEN")


def test_require_env_blank_raises(monkeypatch):
    monkeypatch.setenv("KAPEX_TEST_TOKEN", "   ")
    with pytest.raises(ToolConfigurationError, match="KAPEX_TEST_TOKEN"):
        require_env("KAPEX_TEST_TOKEN")


# ── cache key never includes headers ─────────────────────────


def test_cache_key_excludes_headers():
    """The key is computed only from method/url/params/body — headers (which
    carry API tokens) are structurally excluded from the signature, so a token
    can never end up hashed into the key."""
    key = _cache_key(_METHOD, _URL, _PARAMS, None, None)
    assert "secret-token" not in key
    assert key == _cache_key(_METHOD, _URL, _PARAMS, None, None)


# ── happy path + caching ─────────────────────────────────────


def test_cached_json_returns_parsed_payload(fake_http):
    fake_http([FakeResponse(200, _PAYLOAD)])
    result = _run(cached_json(_METHOD, _URL, params=_PARAMS, headers=_HEADERS))
    assert result == _PAYLOAD


def test_cached_json_reuses_cache_without_second_request(fake_http):
    client = fake_http([FakeResponse(200, _PAYLOAD)])
    first = _run(cached_json(_METHOD, _URL, params=_PARAMS))
    second = _run(cached_json(_METHOD, _URL, params=_PARAMS))
    assert first == second == _PAYLOAD
    assert len(client.calls) == 1  # second read served from Redis


def test_cached_json_sets_ttl(fake_http):
    fake_http([FakeResponse(200, _PAYLOAD)])
    _run(cached_json(_METHOD, _URL, params=_PARAMS, ttl_seconds=60))
    key = _cache_key(_METHOD, _URL, _PARAMS, None, None)
    ttl = _run(redis.ttl(key))
    assert 0 < ttl <= 60


def test_cached_json_ignores_corrupt_cache_and_refetches(fake_http):
    key = _cache_key(_METHOD, _URL, _PARAMS, None, None)
    _run(redis.set(key, "definitely-not-json"))
    client = fake_http([FakeResponse(200, _PAYLOAD)])
    result = _run(cached_json(_METHOD, _URL, params=_PARAMS))
    assert result == _PAYLOAD
    assert len(client.calls) == 1


# ── retry / error handling ───────────────────────────────────


def test_cached_json_retries_transient_errors(fake_http):
    client = fake_http(
        [
            FakeResponse(503, {"error": "unavailable"}),
            FakeResponse(200, _PAYLOAD),
        ]
    )
    result = _run(cached_json(_METHOD, _URL, params=_PARAMS))
    assert result == _PAYLOAD
    assert len(client.calls) == 2


def test_cached_json_transport_error_raises_toolservice(fake_http):
    fake_http([httpx.TransportError("connection refused")] * 3)
    with pytest.raises(ToolServiceError):
        _run(cached_json(_METHOD, _URL, params=_PARAMS))


def test_cached_json_http_error_raises_toolservice(fake_http):
    fake_http([FakeResponse(500, {"error": "boom"})])
    with pytest.raises(ToolServiceError):
        _run(cached_json(_METHOD, _URL, params=_PARAMS))


def test_cached_json_malformed_body_raises_toolservice(fake_http):
    fake_http([FakeResponse(200, "not json at all")])
    with pytest.raises(ToolServiceError):
        _run(cached_json(_METHOD, _URL, params=_PARAMS))