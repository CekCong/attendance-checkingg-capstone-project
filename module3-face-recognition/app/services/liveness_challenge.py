"""Short-lived, one-time liveness challenges stored in Redis."""

import json
import os
import secrets
from functools import lru_cache

import redis


CHALLENGE_TTL_SECONDS = int(os.getenv("LIVENESS_CHALLENGE_TTL_SECONDS", "60"))
CHALLENGE_TYPES = ("blink", "head_turn", "smile")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")


@lru_cache(maxsize=1)
def redis_client():
    return redis.Redis.from_url(
        REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )


def create_liveness_challenge(user_id, session_id):
    """Create a random active challenge without storing biometric data."""
    challenge_id = secrets.token_urlsafe(32)
    challenge_type = secrets.choice(CHALLENGE_TYPES)
    data = json.dumps({
        "user_id": user_id,
        "session_id": session_id,
        "challenge_type": challenge_type,
    })
    redis_client().setex(
        f"liveness:challenge:{challenge_id}",
        CHALLENGE_TTL_SECONDS,
        data,
    )
    return challenge_id, challenge_type


def consume_liveness_challenge(challenge_id, user_id, session_id, challenge_type):
    """Atomically consume and validate a challenge, rejecting reuse."""
    data = redis_client().getdel(f"liveness:challenge:{challenge_id}")
    if data is None:
        return False, "Challenge is expired, invalid, or already used."

    try:
        challenge = json.loads(data)
    except (TypeError, ValueError):
        return False, "Challenge data is invalid."

    if challenge.get("user_id") != user_id:
        return False, "Challenge does not belong to this user."
    if challenge.get("session_id") != session_id:
        return False, "Challenge does not belong to this session."
    if challenge.get("challenge_type") != challenge_type:
        return False, "Challenge action does not match."
    return True, None
