"""Redis-based rate limiting with an in-memory fallback for local UI work."""

from __future__ import annotations

import os
import time
from typing import Tuple

LOGIN_LIMIT = 100000
LOGIN_WINDOW_SECONDS = 3600

_memory_hits: dict[str, list[float]] = {}
_redis = None
_redis_checked = False


def _get_redis():
    global _redis, _redis_checked
    if _redis_checked:
        return _redis
    _redis_checked = True
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
    client = _get_redis()
    if client is not None:
        try:
            current = client.incr(key)
            if current == 1:
                client.expire(key, window)
            ttl = client.ttl(key)
            if ttl < 0:
                client.expire(key, window)
            if current > limit:
                return False, 0
            return True, max(0, limit - current)
        except Exception:
            pass

    now = time.time()
    hits = [t for t in _memory_hits.get(key, []) if now - t < window]
    if len(hits) >= limit:
        _memory_hits[key] = hits
        return False, 0
    hits.append(now)
    _memory_hits[key] = hits
    return True, max(0, limit - len(hits))


def client_ip(request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def login_allowed(request) -> Tuple[bool, int]:
    ip = client_ip(request)
    return check_rate_limit(f"rl:login:{ip}", LOGIN_LIMIT, LOGIN_WINDOW_SECONDS)
