"""Authentication endpoints — matching production spec requirements."""

from __future__ import annotations

from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, JSON, ForeignKey, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from passlib.context import CryptContext
import os
from dotenv import load_dotenv
import uuid
import redis

from ..rate_limit import login_allowed
from ..security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
    user_response,
)
from ..store import create_user, get_by_email, get_by_id, verify_password

# Environment Configuration & Database Setup

load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql://postgres:your_password@localhost:5432/your_database"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

router = APIRouter(prefix="/auth", tags=["auth"])
MAX_FAILED_ATTEMPTS = 10
Role = Literal["student", "ta", "instructor", "admin"]
REFRESH_COOKIE = "refresh_token"

redis_client = redis.Redis()

def check_rate_limit(key: str, limit: int, window: int) -> bool:
    current = redis_client.get(key)
    if current and int(current) >= limit:
        return False
    pipe = redis_client.pipeline()
    pipe.incr(key)
    pipe.expire(key, window)
    pipe.execute()
    return True


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

class RegisterBody(BaseModel):
    email: EmailStr
    password: str
    full_name: str = Field(min_length=1)
    role: Role = "student"

class UserModel(Base):
    __tablename__ = "users"
    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    failed_login_attempts = Column(Integer, nullable=False, default=0)  # Tracks consecutive failures


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


### 3. Register Endpoint with Rate Limiting & Hashing
@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(body: RegisterBody, request: Request, db: Session = Depends(get_db)):
    # Rate Limiting: 10 registrations per 1 hour keyed by IP address
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"rate_limit:register:{client_ip}", limit=10, window=3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many registration attempts. Please try again later.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    if len(body.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="password too weak",
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
    # Rate Limiting: 60 login attempts per 1 hour keyed by IP address
    client_ip = request.client.host if request.client else "unknown"
    if not check_rate_limit(f"rate_limit:login:{client_ip}", limit=60, window=3600):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many login attempts. Try again later.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    email = body.email.lower().strip()

    existing = db.query(UserModel).filter(UserModel.email == email).first()
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    # Check if account is blocked due to 10+ consecutive failed attempts
    if existing.failed_login_attempts >= MAX_FAILED_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account has been blocked due to excessive failed login attempts.",
            headers={"X-RateLimit-Remaining": "0"},
        )

    if not existing.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account disabled",
        )

    # Verify Password
    password_valid = verify_password(body.password, existing.hashed_password)

    if not password_valid:
        existing.failed_login_attempts += 1
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
    db.commit()
    db.refresh(existing)

    user = existing
    access = create_access_token(user)
    refresh_token = create_refresh_token(user)
    _set_refresh_cookie(response, refresh_token)

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