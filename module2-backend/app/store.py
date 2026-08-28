"""In-memory user store — replace with the database in a later iteration."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

USERS: Dict[str, Dict[str, Any]] = {}
USERS_BY_EMAIL: Dict[str, str] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def public_user(user: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": user["id"],
        "email": user["email"],
        "full_name": user["full_name"],
        "role": user["role"],
        "is_active": user["is_active"],
        "camera_consent": user.get("camera_consent", False),
        "geolocation_consent": user.get("geolocation_consent", False),
        "face_enrolled": user.get("face_enrolled", False),
        "created_at": user["created_at"],
    }


def create_user(
    email: str,
    password: str,
    full_name: str,
    role: str = "student",
) -> Dict[str, Any]:
    user_id = str(uuid4())
    user = {
        "id": user_id,
        "email": email.lower(),
        "password_hash": hash_password(password),
        "full_name": full_name,
        "role": role,
        "is_active": True,
        "camera_consent": False,
        "geolocation_consent": False,
        "face_enrolled": False,
        "strict_password": True,
        "created_at": _now(),
    }
    USERS[user_id] = user
    USERS_BY_EMAIL[email.lower()] = user_id
    return user


def get_by_email(email: str) -> Optional[Dict[str, Any]]:
    user_id = USERS_BY_EMAIL.get(email.lower())
    if not user_id:
        return None
    return USERS.get(user_id)


def get_by_id(user_id: str) -> Optional[Dict[str, Any]]:
    return USERS.get(user_id)


def list_users() -> list[Dict[str, Any]]:
    return [public_user(u) for u in USERS.values()]
