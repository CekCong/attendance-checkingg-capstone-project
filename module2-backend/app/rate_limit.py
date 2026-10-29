"""Shared Redis rate limits; optional memory fallback for isolated development."""

from __future__ import annotations

import os
import time
from typing import Tuple
from fastapi import HTTPException

LOGIN_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "60"))
LOGIN_WINDOW_SECONDS = 3600

_memory_hits: dict[str, list[float]] = {}
_redis = None


def _get_redis():
    global _redis
    if _redis is not None:
        return _redis
    try:
        import redis as redis_lib

        redis_url = os.getenv("REDIS_URL")
        if redis_url:
            client = redis_lib.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=0.15,
                socket_timeout=0.15,
            )
        else:
            client = redis_lib.Redis(
                host=os.getenv("REDIS_HOST", "localhost"),
                port=int(os.getenv("REDIS_PORT", "6380")),
                db=int(os.getenv("REDIS_DB", "0")),
                decode_responses=True,
                socket_connect_timeout=0.15,
                socket_timeout=0.15,
            )
        client.ping()
        _redis = client
    except Exception:
        _redis = None
    return _redis


def get_redis_client():
    """Return the shared Redis client, or None when Redis is unavailable."""
    return _get_redis()


def check_rate_limit(key: str, limit: int, window: int) -> Tuple[bool, int]:
    """
    Return (allowed, remaining). Increments the counter when allowed.
    """
    key = os.getenv("RATE_LIMIT_PREFIX", "saiv:rate-limit:") + key
    client = _get_redis()
    if client is not None:
        try:
            current = int(client.eval("""
                local count = redis.call('INCR', KEYS[1])
                if redis.call('TTL', KEYS[1]) < 0 then
                    redis.call('EXPIRE', KEYS[1], ARGV[1])
                end
                return count
            """, 1, key, window))
            if current > limit:
                return False, 0
            return True, max(0, limit - current)
        except Exception:
            pass

    if os.getenv("RATE_LIMIT_ALLOW_MEMORY", "false").lower() != "true":
        raise HTTPException(status_code=503, detail="Rate limit service unavailable")

    now = time.time()
    hits = [t for t in _memory_hits.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _memory_hits[key] = hits
        return False, 0
    hits.append(now)
    _memory_hits[key] = hits
    return True, max(0, limit - len(hits))


def client_ip(request) -> str:
    # Forwarded headers must be validated by a trusted ingress/ASGI server.
    return request.client.host if request.client else "unknown"


def login_allowed(request) -> Tuple[bool, int]:
    ip = client_ip(request)
    return check_rate_limit(f"rl:login:{ip}", LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)


def enforce_rate_limit(key: str, limit: int, window: int) -> None:
    allowed, remaining = check_rate_limit(key, limit, window)
    if not allowed:
        raise HTTPException(
            status_code=429, detail="Too many requests",
            headers={"X-RateLimit-Remaining": str(remaining), "Retry-After": str(window)},
        )
