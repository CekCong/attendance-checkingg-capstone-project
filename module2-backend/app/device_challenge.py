"""Short-lived, one-time challenges for device attestation."""

import hashlib
import json
import os
import secrets

from .rate_limit import get_redis_client


DEVICE_CHALLENGE_TTL_SECONDS = int(os.getenv("DEVICE_CHALLENGE_TTL_SECONDS", "120"))


class DeviceChallengeStoreError(Exception):
    """Raised when the Redis-backed challenge store is unavailable."""


def _challenge_key(challenge: str) -> str:
    digest = hashlib.sha256(challenge.encode("utf-8")).hexdigest()
    return f"device_challenge:{digest}"


def create_device_challenge(user_id: str, device_id: str, session_id: str) -> str:
    client = get_redis_client()
    if client is None:
        raise DeviceChallengeStoreError("Device challenge store is unavailable")

    challenge = secrets.token_urlsafe(32)
    data = json.dumps({
        "user_id": user_id,
        "device_id": device_id,
        "session_id": session_id,
    })
    try:
        client.setex(_challenge_key(challenge), DEVICE_CHALLENGE_TTL_SECONDS, data)
    except Exception as exc:
        raise DeviceChallengeStoreError("Device challenge store is unavailable") from exc
    return challenge


def consume_device_challenge(
    challenge: str,
    user_id: str,
    device_id: str,
    session_id: str,
) -> bool:
    client = get_redis_client()
    if client is None:
        raise DeviceChallengeStoreError("Device challenge store is unavailable")

    try:
        raw_data = client.getdel(_challenge_key(challenge))
    except Exception as exc:
        raise DeviceChallengeStoreError("Device challenge store is unavailable") from exc
    if raw_data is None:
        return False

    try:
        data = json.loads(raw_data)
    except (TypeError, ValueError):
        return False
    return data == {
        "user_id": user_id,
        "device_id": device_id,
        "session_id": session_id,
    }
