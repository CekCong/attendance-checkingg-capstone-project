"""Authentication endpoints — stub logic suitable for UI work."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field

from ..rate_limit import login_allowed
from ..security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    user_response,
)
from ..store import create_user, get_by_email, get_by_id, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])

Role = Literal["student", "ta", "instructor", "admin"]

REFRESH_COOKIE = "refresh_token"


class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    role: Role = "student"


class LoginBody(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)
    role: Optional[Role] = None


class RefreshBody(BaseModel):
    refresh_token: Optional[str] = None


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        secure=False,
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterBody):
    if get_by_email(body.email):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")
    user = create_user(body.email, body.password, body.full_name, body.role)
    return user_response(user)


@router.post("/login")
async def login(body: LoginBody, request: Request, response: Response):
    allowed, remaining = login_allowed(request)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    existing = get_by_email(body.email)
    if existing:
        if not existing.get("is_active", True):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
        if existing.get("strict_password", True) and not verify_password(
            body.password, existing["password_hash"]
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        if body.role:
            existing["role"] = body.role
        user = existing
    else:
        # UI stub: any username/password that is not a registered account is accepted.
        role = body.role or "student"
        local = body.email.split("@")[0] or "User"
        user = create_user(body.email, body.password, local.replace(".", " ").title(), role)
        user["strict_password"] = False

    access = create_access_token(user)
    refresh = create_refresh_token(user)
    _set_refresh_cookie(response, refresh)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user": user_response(user),
    }


@router.post("/refresh")
async def refresh(body: RefreshBody, request: Request, response: Response):
    token = body.refresh_token or request.cookies.get(REFRESH_COOKIE)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    payload = decode_token(token, expected_type="refresh")
    user = get_by_id(payload.get("sub", ""))
    if user is None:
        user = {
            "id": payload.get("sub"),
            "email": payload.get("email"),
            "full_name": payload.get("email"),
            "role": payload.get("role", "student"),
            "is_active": True,
        }
    access = create_access_token(user)
    new_refresh = create_refresh_token(user)
    _set_refresh_cookie(response, new_refresh)
    return {
        "access_token": access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
    }


@router.post("/logout")
async def logout(response: Response, _user=Depends(get_current_user)):
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user_response(user)
