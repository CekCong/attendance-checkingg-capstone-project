"""Authentication endpoints — matching production spec requirements."""

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
    password: str
    full_name: str = Field(min_length=1)
    role: Role = "student"


class LoginBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


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
    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="password too weak",
        )

    if get_by_email(body.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

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
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not existing.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    if not verify_password(body.password, existing.get("hashed_password") or existing.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    user = existing
    access = create_access_token(user)
    refresh_token = create_refresh_token(user)
    _set_refresh_cookie(response, refresh_token)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    
    return {
        "access_token": access,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_response(user),
    }


@router.post("/refresh")
async def refresh(body: Optional[RefreshBody] = None, request: Request = None, response: Response = None):
    # Retrieve token from JSON body or fall back to HTTP-only cookie
    token = (body.refresh_token if body else None) or (request.cookies.get(REFRESH_COOKIE) if request else None)
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing refresh token",
        )

    try:
        payload = decode_token(token, expected_type="refresh")
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing refresh token",
        )

    user = get_by_id(payload.get("sub", ""))
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing refresh token",
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    new_access = create_access_token(user)
    new_refresh = create_refresh_token(user)
    
    if response:
        _set_refresh_cookie(response, new_refresh)

    return {
        "access_token": new_access,
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