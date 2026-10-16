import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum, create_engine, func, or_
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import enum
import os
import httpx
from models import UserModel as User

from app.security import get_current_user, require_roles

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


# --- Pydantic Schemas ---
class UpdateMeBody(BaseModel):
    full_name: Optional[str] = Field(None, max_length=255)
    camera_consent: Optional[bool] = None
    geolocation_consent: Optional[bool] = None

class AdminUpdateUserBody(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

# Request schema for POST /users/me/face/enroll
class FaceEnrollBody(BaseModel):
    image: str = Field(..., description="Base64-encoded face image (PNG/JPEG), without data URL prefix")

# Response schema for POST /users/me/face/enroll
class FaceEnrollResponse(BaseModel):
    success: bool
    message: str
    face_enrolled: bool
    quality_score: float

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    camera_consent: bool
    geolocation_consent: bool
    face_enrolled: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserListItemResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    face_enrolled: bool
    created_at: datetime

    class Config:
        from_attributes = True

class UserListResponse(BaseModel):
    items: List[UserListItemResponse]
    total: int
    limit: int
    offset: int



# Stub for external face recognition service processing
FACE_SERVICE_URL = os.getenv(
    "FACE_SERVICE_URL", "http://localhost:8001"
).rstrip("/")


def process_face_enrollment(image_base64: str, user_id: str) -> tuple[str, float]:
    try:
        with httpx.Client(timeout=15) as client:
            response = client.post(
                f"{FACE_SERVICE_URL}/face/enroll",
                json={
                    "user_id": user_id,
                    "image": image_base64,
                    "camera_consent": True,
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Face recognition service unavailable",
        ) from exc

    if response.status_code == 400:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Face image could not be enrolled",
        )

    try:
        response.raise_for_status()
        result = response.json()
        return result["face_template_hash"], result["quality_score"]
    except (httpx.HTTPStatusError, ValueError, KeyError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Face recognition service returned an invalid response",
        ) from exc

router = APIRouter(prefix="/users", tags=["users"])

# GET /users/me
@router.get("/me", response_model=UserResponse)
def get_me(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.get("id")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


# PUT /users/me
@router.put("/me", response_model=UserResponse)
def update_me(
    body: UpdateMeBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.get("id")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    if "full_name" in update_data and update_data["full_name"]:
        update_data["full_name"] = update_data["full_name"].strip()

    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user


# POST /users/me/face/enroll
@router.post("/me/face/enroll", response_model=FaceEnrollResponse)
def enroll_face(
    body: FaceEnrollBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.get("id")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    # Prerequisite check: camera_consent must be True
    if not user.camera_consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera consent not given"
        )

    # Call face recognition service stub
    embedding_hash, quality_score = process_face_enrollment(body.image, user.id)

    # Update database record upon successful processing
    user.face_embedding_hash = embedding_hash
    user.face_enrolled = True

    db.commit()

    return {
        "success": True,
        "message": "Face enrolled successfully",
        "face_enrolled": True,
        "quality_score": quality_score
    }


# GET /users/
@router.get("/", response_model=UserListResponse)
def list_all_users(
    role: Optional[UserRole] = Query(None, description="Filter by role"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by name or email"),
    limit: int = Query(50, ge=1, le=100, description="Results per page (max 100)"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    query = db.query(User)

    if role:
        query = query.filter(User.role == role)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)
    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(search_pattern),
                User.email.ilike(search_pattern)
            )
        )

    total = query.count()
    items = query.offset(offset).limit(limit).all()

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# GET /users/{user_id}
@router.get("/{user_id}", response_model=UserResponse)
def get_user(
    user_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    current_role = current_user.get("role")
    
    if current_role not in {"admin", "instructor", "ta"} and current_user.get("id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    return user


# PATCH /users/{user_id}
@router.patch("/{user_id}", response_model=UserResponse)
def update_user_details(
    user_id: str,
    body: AdminUpdateUserBody,
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(user, field, value)

    db.commit()
    db.refresh(user)
    return user