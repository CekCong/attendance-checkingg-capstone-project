import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum, ForeignKey, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import enum
import os
from dotenv import load_dotenv

from security import get_current_user

# --- Database Setup ---
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

# --- Enums & SQLAlchemy Models ---
class UserRole(str, enum.Enum):
    student = "student"
    instructor = "instructor"
    ta = "ta"
    admin = "admin"

class SessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    active = "active"
    closed = "closed"
    cancelled = "cancelled"

from models import UserModel as User, SessionModel

class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"

    id = Column(String(36), primary_key=True)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default="student")
    created_at = Column(DateTime, nullable=False, server_default=func.now())

# --- Pydantic Schemas ---
class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    role: UserRole

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class SessionStatusUpdate(BaseModel):
    status: SessionStatus

class EnrollmentCreate(BaseModel):
    course_id: str
    user_id: str
    role: Optional[str] = "student"

class EnrollmentResponse(BaseModel):
    id: str
    course_id: str
    user_id: str
    role: str
    created_at: datetime

    class Config:
        from_attributes = True

# --- Password Helper ---
def hash_password(password: str) -> str:
    return f"hashed_{password}"

# --- Admin Guard Helper ---
def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)):
    if current_user.get("role") != UserRole.admin.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin privileges required."
        )
    return current_user

# --- Router Implementation (admin.py) ---
router = APIRouter(prefix="/admin", tags=["Admin Operations"])


# PATCH /admin/users/{user_id}/deactivate - Deactivate user
@router.patch("/users/{user_id}/deactivate", response_model=UserResponse)
def deactivate_user(
    user_id: str,
    _: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")

    user.is_active = False
    db.commit()
    db.refresh(user)
    return user


# PATCH /admin/users/{user_id}/activate - Activate user
@router.patch("/users/{user_id}/activate", response_model=UserResponse)
def activate_user(
    user_id: str,
    _: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")

    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


# POST /admin/users/bulk - Bulk create users
@router.post("/users/bulk", response_model=List[UserResponse], status_code=status.HTTP_201_CREATED)
def bulk_create_users(
    users_data: List[UserCreate],
    _: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    created_users = []
    
    # Pre-check for duplicate emails within payload or DB
    emails = [u.email for u in users_data]
    existing_emails = {
        u.email for u in db.query(User.email).filter(User.email.in_(emails)).all()
    }
    
    if existing_emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The following emails already exist: {', '.join(existing_emails)}"
        )

    for data in users_data:
        user = User(
            id=str(uuid.uuid4()),
            email=data.email,
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            role=data.role,
            is_active=True
        )
        db.add(user)
        created_users.append(user)

    try:
        db.commit()
        for user in created_users:
            db.refresh(user)
        return created_users
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to bulk create users: {str(e)}"
        )


# PATCH /admin/sessions/{session_id}/status - Update session status
@router.patch("/sessions/{session_id}/status", status_code=status.HTTP_200_OK)
def update_session_status(
    session_id: str,
    payload: SessionStatusUpdate,
    _: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found."
        )

    session_obj.status = payload.status
    db.commit()
    return {"message": f"Session status updated to '{payload.status.value}' successfully."}


# POST /admin/enrollments/ - Admin enrollment creation
@router.post("/enrollments/", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment(
    payload: EnrollmentCreate,
    _: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    enrollment = CourseEnrollment(
        id=str(uuid.uuid4()),
        course_id=payload.course_id,
        user_id=payload.user_id,
        role=payload.role
    )

    try:
        db.add(enrollment)
        db.commit()
        db.refresh(enrollment)
        return enrollment
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create enrollment: {str(e)}"
        )