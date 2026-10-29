"""Authentication endpoints — matching production spec requirements."""

from __future__ import annotations

import html
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from passlib.context import CryptContext
import os
from dotenv import load_dotenv
import uuid
from ..rate_limit import check_rate_limit as apply_rate_limit, enforce_rate_limit
from ..audit import add_audit_log
from ..security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    user_response,
)

# Environment Configuration & Database Setup

load_dotenv()
from ..database import get_db
from ..models import UserModel

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:your_password@localhost:5432/your_database"
)

router = APIRouter(prefix="/auth", tags=["auth"])
MAX_FAILED_ATTEMPTS = 10
Role = Literal["student", "ta", "instructor", "admin"]
REFRESH_COOKIE = "refresh_token"
REGISTRATION_RATE_LIMIT = int(os.getenv("REGISTRATION_RATE_LIMIT", "10"))
LOGIN_RATE_LIMIT = int(os.getenv("LOGIN_RATE_LIMIT", "60"))

def check_rate_limit(key: str, limit: int, window: int) -> bool:
    allowed, _remaining = apply_rate_limit(key, limit, window)
    return allowed


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

class RegisterBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str = Field(min_length=1)
    role: Role = "student"

    @field_validator("full_name")
    @classmethod
    def escape_full_name(cls, value: str) -> str:
        return html.escape(value, quote=False)

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
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        max_age=7 * 24 * 60 * 60,
        path="/",
    )


### 3. Register Endpoint with Rate Limiting & Hashing
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterBody, request: Request, db: Session = Depends(get_db)):
    ### Rate Limiting: configurable registrations per hour keyed by IP address
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(
        f"rate_limit:register:{client_ip}",
        limit=REGISTRATION_RATE_LIMIT,
        window=3600,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    existing_user = db.query(UserModel).filter(UserModel.email == body.email.lower().strip()).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Securely hash the password
    hashed_password = get_password_hash(body.password)

    new_user = UserModel(
        id=str(uuid.uuid4()),
        email=body.email.lower().strip(),
        full_name=body.full_name,
        hashed_password=hashed_password,
        role=body.role,
        is_active=True,
        failed_login_attempts=0
    )

    db.add(new_user)
    db.flush()
    add_audit_log(
        db,
        request,
        "user_created",
        user_id=new_user.id,
        resource_type="user",
        resource_id=new_user.id,
    )
    db.commit()
    db.refresh(new_user)

    return user_response(new_user)


### 4. Login Endpoint with Rate Limiting & Failed Attempt Protection
@router.post("/login")
async def login(
    body: LoginBody, 
    request: Request, 
    response: Response, 
    db: Session = Depends(get_db)
):
    # Rate limit login attempts per hour, keyed by peer IP.
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(
        f"rate_limit:login:{client_ip}",
        limit=LOGIN_RATE_LIMIT,
        window=3600,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    email = body.email.lower().strip()

    existing = db.query(UserModel).filter(UserModel.email == email).first()
    if not existing:
        add_audit_log(
            db,
            request,
            "login_failed",
            resource_type="user",
            details="Invalid credentials",
            success=False,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if account is blocked due to 10+ consecutive failed attempts
    if existing.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        add_audit_log(
            db,
            request,
            "login_failed",
            user_id=existing.id,
            resource_type="user",
            resource_id=existing.id,
            details="Account blocked after repeated failed login attempts",
            success=False,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account has been blocked due to excessive failed login attempts.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    if not existing.is_active:
        add_audit_log(
            db,
            request,
            "login_failed",
            user_id=existing.id,
            resource_type="user",
            resource_id=existing.id,
            details="Account disabled",
            success=False,
        )
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    # Verify Password
    password_valid = verify_password(body.password, existing.hashed_password)

    if not password_valid:
        existing.failed_login_attempts += 1
        add_audit_log(
            db,
            request,
            "login_failed",
            user_id=existing.id,
            resource_type="user",
            resource_id=existing.id,
            details="Invalid credentials",
            success=False,
        )
        db.commit()

        if existing.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account has been blocked due to 10 consecutive failed login attempts.",
                headers={"X-RateLimit-Remaining": "0"},
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Successful login: Reset counter and update timestamp
    existing.failed_login_attempts = 0
    existing.last_login_at = datetime.utcnow()
    add_audit_log(
        db,
        request,
        "login_success",
        user_id=existing.id,
        resource_type="user",
        resource_id=existing.id,
    )
    db.commit()
    db.refresh(existing)

    token_user = {"id": existing.id, "email": existing.email, "role": existing.role}
    access = create_access_token(token_user)
    refresh_token = create_refresh_token(token_user)
    _set_refresh_cookie(response, refresh_token)

    return {
        "access_token": access,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "user": user_response(existing),
    }

@router.post("/refresh")
async def refresh(
    body: Optional[RefreshBody] = None,
    request: Request = None,
    response: Response = None,
    db: Session = Depends(get_db),
):
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

    user = db.query(UserModel).filter(UserModel.id == payload.get("sub", "")).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing refresh token",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    enforce_rate_limit(f"api:{user.id}", int(os.getenv("API_RATE_LIMIT", "1000")), 3600)
    token_user = {"id": user.id, "email": user.email, "role": user.role}
    new_access = create_access_token(token_user)
    new_refresh = create_refresh_token(token_user)
    
    if response:
        _set_refresh_cookie(response, new_refresh)

    return {
        "access_token": new_access,
        "refresh_token": new_refresh,
        "token_type": "bearer",
        "user": user_response(user),
    }


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    _user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    add_audit_log(
        db,
        request,
        "logout",
        user_id=str(_user.get("id")),
        resource_type="user",
        resource_id=str(_user.get("id")),
    )
    db.commit()
    response.delete_cookie(REFRESH_COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(get_current_user)):
    return user_response(user)