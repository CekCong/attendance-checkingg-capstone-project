import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Response, Request
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import enum

# Import authentication helper from security.py as specified
from security import get_current_user

# --- Database & Base Setup ---
DATABASE_URL = "postgresql://postgres:password@localhost:5432/postgres"
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- SQLAlchemy Model ---
class UserRole(str, enum.Enum):
    student = "student"
    instructor = "instructor"
    ta = "ta"
    admin = "admin"

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(SQLEnum(UserRole), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    camera_consent = Column(Boolean, default=False)
    geolocation_consent = Column(Boolean, default=False)
    face_embedding_hash = Column(String(64), nullable=True)
    face_enrolled = Column(Boolean, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())
    last_login_at = Column(DateTime, nullable=True)
    scheduled_deletion_at = Column(DateTime, nullable=True)

# --- Pydantic Request/Response Models ---
class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    camera_consent: bool
    geolocation_consent: bool
    face_enrolled: bool

    class Config:
        from_attributes = True

class ConsentUpdateRequest(BaseModel):
    camera_consent: Optional[bool] = None
    geolocation_consent: Optional[bool] = None

# --- Router Implementation (auth.py) ---
router = APIRouter(prefix="/auth", tags=["Auth"])

# Placeholder helper functions for token generation/hashing logic
def hash_password(password: str) -> str:
    return f"hashed_{password}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hashed_password == f"hashed_{plain_password}"

def create_tokens(user_id: str, email: str, role: str) -> Dict[str, str]:
    return {
        "access_token": f"access_token_for_{user_id}",
        "refresh_token": f"refresh_token_for_{user_id}"
    }

# POST /auth/register
@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: UserRegisterRequest, db: Session = Depends(get_db)):
    existing_user = db.query(User).filter(User.email == payload.email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email address already registered."
        )

    new_user = User(
        id=str(uuid.uuid4()),
        email=payload.email,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=payload.role,
        is_active=True,
        camera_consent=False,
        geolocation_consent=False,
        face_enrolled=False
    )
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

# POST /auth/login
@router.post("/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")

    user.last_login_at = datetime.now(timezone.utc)
    db.commit()

    tokens = create_tokens(user.id, user.email, user.role.value)
    return TokenResponse(
        access_token=tokens["access_token"],
        refresh_token=tokens["refresh_token"]
    )

# POST /auth/refresh
@router.post("/refresh", response_model=TokenResponse)
def refresh_token(request: Request):
    # Retrieve refresh token from authorization header or payload body
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token."
        )
    
    # Process and return new access & refresh token pair
    return TokenResponse(
        access_token="new_access_token",
        refresh_token="new_refresh_token"
    )

# POST /auth/logout
@router.post("/logout", status_code=status.HTTP_200_OK)
def logout(current_user: Dict[str, Any] = Depends(get_current_user)):
    # Invalidates active tokens/sessions if using blacklists or DB sessions
    return {"message": "Successfully logged out."}

# GET /auth/me
@router.get("/me", response_model=UserResponse)
def get_me(current_user: Dict[str, Any] = Depends(get_current_user)):
    return current_user

# PATCH /auth/me
@router.patch("/me", response_model=UserResponse)
def update_consent(
    payload: ConsentUpdateRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user.get("id")
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found."
        )

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user