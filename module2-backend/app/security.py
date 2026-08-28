"""JWT helpers and RBAC dependencies."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from .store import get_by_id, public_user

SECRET_KEY = os.getenv("SECRET_KEY", "saiv-dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_TTL = timedelta(hours=1)
REFRESH_TOKEN_TTL = timedelta(days=7)

ROLE_LEVEL = {
    "student": 1,
    "ta": 2,
    "instructor": 3,
    "admin": 4,
}

bearer_scheme = HTTPBearer(auto_error=False)


def create_token(subject: Dict[str, Any], token_type: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject["id"],
        "email": subject["email"],
        "role": subject["role"],
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def create_access_token(user: Dict[str, Any]) -> str:
    return create_token(user, "access", ACCESS_TOKEN_TTL)


def create_refresh_token(user: Dict[str, Any]) -> str:
    return create_token(user, "refresh", REFRESH_TOKEN_TTL)


def decode_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        ) from exc
    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )
    return payload


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> Dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(credentials.credentials, expected_type="access")
    user = get_by_id(payload.get("sub", ""))
    if user is None:
        # Stub tokens may refer to ephemeral users created at login time
        user = {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "full_name": payload.get("email", "User").split("@")[0],
            "role": payload.get("role", "student"),
            "is_active": True,
            "camera_consent": False,
            "geolocation_consent": False,
            "face_enrolled": False,
            "created_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z"),
        }
    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    return user


def require_roles(*roles: str):
    allowed = set(roles)

    async def _checker(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        if user.get("role") not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return _checker


def has_at_least(user: Dict[str, Any], role: str) -> bool:
    return ROLE_LEVEL.get(user.get("role", ""), 0) >= ROLE_LEVEL.get(role, 99)


def user_response(user: Dict[str, Any]) -> Dict[str, Any]:
    if "password_hash" in user or "created_at" in user:
        try:
            return public_user(user)
        except Exception:
            pass
    return {
        "id": user.get("id"),
        "email": user.get("email"),
        "full_name": user.get("full_name"),
        "role": user.get("role"),
        "is_active": user.get("is_active", True),
        "camera_consent": user.get("camera_consent", False),
        "geolocation_consent": user.get("geolocation_consent", False),
        "face_enrolled": user.get("face_enrolled", False),
        "created_at": user.get("created_at"),
    }
