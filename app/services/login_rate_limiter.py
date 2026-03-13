"""Best-effort login rate limiting with Redis + in-memory fallback."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import redis.asyncio as aioredis

from app.config import get_settings

logger = logging.getLogger(__name__)

MAX_FAILED_ATTEMPTS = 10
WINDOW_SECONDS = 60
_KEY_PREFIX = "aso:auth:login_failed"

_redis_client: Optional[aioredis.Redis] = None
_redis_lock = asyncio.Lock()
_redis_retry_after = 0.0

_local_store: dict[str, dict[str, float]] = {}
_local_lock = asyncio.Lock()


def _now() -> float:
    return time.monotonic()


def _key(client_ip: str) -> str:
    return f"{_KEY_PREFIX}:{client_ip}"


async def _get_redis_client() -> Optional[aioredis.Redis]:
    """Return a healthy Redis client, or None when Redis is unavailable."""
    global _redis_client, _redis_retry_after

    if _redis_client is not None:
        return _redis_client

    if _now() < _redis_retry_after:
        return None

    async with _redis_lock:
        if _redis_client is not None:
            return _redis_client
        if _now() < _redis_retry_after:
            return None

        try:
            client = aioredis.from_url(
                get_settings().redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=1,
                socket_timeout=1,
            )
            await client.ping()
            _redis_client = client
            return _redis_client
        except Exception as exc:  # pragma: no cover - exercised only when Redis is down
            _redis_retry_after = _now() + 10
            logger.warning("Login rate limiter Redis unavailable; falling back to in-memory store: %s", exc)
            return None


async def _redis_get_attempts(client_ip: str) -> Optional[int]:
    client = await _get_redis_client()
    if client is None:
        return None

    try:
        raw = await client.get(_key(client_ip))
        return int(raw or 0)
    except Exception as exc:  # pragma: no cover - exercised only when Redis flaps
        logger.warning("Login rate limiter Redis read failed; using in-memory fallback: %s", exc)
        return None


async def _redis_increment_failure(client_ip: str) -> Optional[int]:
    client = await _get_redis_client()
    if client is None:
        return None

    try:
        counter_key = _key(client_ip)
        count = await client.incr(counter_key)
        if count == 1:
            await client.expire(counter_key, WINDOW_SECONDS)
        return int(count)
    except Exception as exc:  # pragma: no cover - exercised only when Redis flaps
        logger.warning("Login rate limiter Redis increment failed; using in-memory fallback: %s", exc)
        return None


async def _redis_clear(client_ip: str) -> bool:
    client = await _get_redis_client()
    if client is None:
        return False

    try:
        await client.delete(_key(client_ip))
        return True
    except Exception as exc:  # pragma: no cover - exercised only when Redis flaps
        logger.warning("Login rate limiter Redis clear failed; using in-memory fallback: %s", exc)
        return False


async def _local_get_attempts(client_ip: str) -> int:
    async with _local_lock:
        entry = _local_store.get(client_ip)
        now = _now()
        if not entry:
            return 0
        if entry["expires_at"] <= now:
            _local_store.pop(client_ip, None)
            return 0
        return int(entry["count"])


async def _local_increment_failure(client_ip: str) -> int:
    async with _local_lock:
        now = _now()
        entry = _local_store.get(client_ip)
        if not entry or entry["expires_at"] <= now:
            count = 1
            expires_at = now + WINDOW_SECONDS
        else:
            count = int(entry["count"]) + 1
            expires_at = entry["expires_at"]
        _local_store[client_ip] = {"count": float(count), "expires_at": expires_at}
        return count


async def _local_clear(client_ip: str) -> None:
    async with _local_lock:
        _local_store.pop(client_ip, None)


async def is_limited(client_ip: str) -> bool:
    attempts = await _redis_get_attempts(client_ip)
    if attempts is None:
        attempts = await _local_get_attempts(client_ip)
    return attempts >= MAX_FAILED_ATTEMPTS


async def record_failure(client_ip: str) -> int:
    attempts = await _redis_increment_failure(client_ip)
    if attempts is None:
        attempts = await _local_increment_failure(client_ip)
    return attempts


async def clear_failures(client_ip: str) -> None:
    cleared = await _redis_clear(client_ip)
    if not cleared:
        await _local_clear(client_ip)


async def reset_rate_limiter_state_for_tests() -> None:
    """Test helper to isolate state across tests."""
    global _redis_client, _redis_retry_after

    async with _local_lock:
        _local_store.clear()

    _redis_retry_after = 0.0
    if _redis_client is not None:
        try:
            await _redis_client.aclose()
        except Exception:
            pass
        _redis_client = None
