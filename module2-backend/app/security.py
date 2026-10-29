"""JWT helpers and RBAC dependencies."""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .database import get_db
from .models import UserModel
from .rate_limit import enforce_rate_limit

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
        "av": subject.get("auth_version", 0),
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


def validate_token_version(payload: Dict[str, Any], user: UserModel) -> None:
    # Tokens issued before this migration deliberately require a new login.
    if payload.get("av") != user.auth_version:
        raise HTTPException(status_code=401, detail="Session revoked. Please sign in again.")


def revoke_user_sessions(db: Session, user_id: str) -> None:
    # SQL increment avoids lost updates when logout and password changes race.
    db.query(UserModel).filter(UserModel.id == user_id).update(
        {UserModel.auth_version: UserModel.auth_version + 1}, synchronize_session=False,
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Dict[str, Any]:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    payload = decode_token(credentials.credentials, expected_type="access")
    user = (
        db.query(UserModel)
        .filter(UserModel.id == payload.get("sub", ""))
        .first()
    )
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )
    if not user.is_active or user.scheduled_deletion_at is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )
    validate_token_version(payload, user)
    if request is not None:
        enforce_rate_limit(
            f"api:{user.id}", int(os.getenv("API_RATE_LIMIT", "1000")), 3600,
        )
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role,
        "is_active": user.is_active,
        "camera_consent": user.camera_consent,
        "geolocation_consent": user.geolocation_consent,
        "face_enrolled": user.face_enrolled,
        "created_at": user.created_at,
    }


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    request: Request = None,
) -> Optional[Dict[str, Any]]:
    if credentials is None:
        return None
    return await get_current_user(credentials, db, request)


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


def user_response(user: Any) -> Dict[str, Any]:
    if not isinstance(user, dict):
        user = {
            field: getattr(user, field)
            for field in (
                "id",
                "email",
                "full_name",
                "role",
                "is_active",
                "camera_consent",
                "geolocation_consent",
                "face_enrolled",
                "created_at",
                "hashed_password",
            )
            if hasattr(user, field)
        }

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
