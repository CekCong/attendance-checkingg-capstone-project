import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator
from sqlalchemy import Column, String, Boolean, DateTime, Enum as SQLEnum, ForeignKey, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import enum
import os
from dotenv import load_dotenv

from app.security import get_current_user, revoke_user_sessions
from app.database import get_db as shared_get_db
from app.models import UserModel as User, SessionModel, EnrollmentModel
from app.store import hash_password
from app.audit import add_audit_log

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
    yield from shared_get_db()

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

class AdminUserStatusResponse(BaseModel):
    id: str
    email: EmailStr
    is_active: bool
    message: str

class BulkUserCreateRequest(BaseModel):
    users: List[UserCreate]

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_list(cls, value):
        return {"users": value} if isinstance(value, list) else value

class BulkUserCreateResponse(BaseModel):
    created: int
    failed: int
    users: List[UserResponse]
    errors: List[str]

    def __getitem__(self, index):
        return self.users[index]

class AdminSessionStatusResponse(BaseModel):
    id: str
    name: str
    status: SessionStatus
    message: str

class SessionStatusUpdate(BaseModel):
    status: SessionStatus

class EnrollmentCreate(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    course_id: str
    user_id: str = Field(alias="student_id")
    role: Optional[str] = "student"

class EnrollmentResponse(BaseModel):
    id: str
    course_id: str
    student_id: str
    is_active: bool
    enrolled_at: datetime

    class Config:
        from_attributes = True

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
@router.patch("/users/{user_id}/deactivate", response_model=AdminUserStatusResponse)
def deactivate_user(
    user_id: str,
    request: Request,
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")

    user.is_active = False
    revoke_user_sessions(db, user.id)
    add_audit_log(
        db, request, "user_updated",
        user_id=str(admin_user.get("id")), resource_type="user", resource_id=user.id,
        details="Account deactivated",
    )
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "message": "User deactivated successfully",
    }


# PATCH /admin/users/{user_id}/activate - Activate user
@router.patch("/users/{user_id}/activate", response_model=AdminUserStatusResponse)
def activate_user(
    user_id: str,
    request: Request,
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")

    if user.scheduled_deletion_at is not None or user.hashed_password == "!deleted":
        raise HTTPException(409, "Accounts scheduled for deletion or erased cannot be activated.")
    user.is_active = True
    add_audit_log(
        db, request, "user_updated",
        user_id=str(admin_user.get("id")), resource_type="user", resource_id=user.id,
        details="Account activated",
    )
    db.commit()
    db.refresh(user)
    return {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "message": "User activated successfully",
    }


# POST /admin/users/bulk - Bulk create users
@router.post("/users/bulk", response_model=BulkUserCreateResponse, status_code=status.HTTP_201_CREATED)
def bulk_create_users(
    users_data: BulkUserCreateRequest,
    request: Request,
    _: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    requested_users = users_data.users if isinstance(users_data, BulkUserCreateRequest) else users_data
    created_users = []
    
    # Pre-check for duplicate emails within payload or DB
    emails = [str(user.email).strip().lower() for user in requested_users]
    if len(set(emails)) != len(emails):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The bulk request contains duplicate email addresses."
        )

    existing_emails = {
        email
        for (email,) in db.query(func.lower(User.email))
        .filter(func.lower(User.email).in_(emails))
        .all()
    }
    
    if existing_emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"The following emails already exist: {', '.join(existing_emails)}"
        )

    for data in requested_users:
        user = User(
            id=str(uuid.uuid4()),
            email=str(data.email).strip().lower(),
            full_name=data.full_name,
            hashed_password=hash_password(data.password),
            role=data.role,
            is_active=True
        )
        db.add(user)
        created_users.append(user)

    try:
        db.flush()
        for user in created_users:
            add_audit_log(
                db,
                request,
                "user_created",
                user_id=user.id,
                resource_type="user",
                resource_id=user.id,
                details="Created by admin bulk-user endpoint",
            )
        db.commit()
        for user in created_users:
            db.refresh(user)
        return BulkUserCreateResponse(
            created=len(created_users),
            failed=0,
            users=[UserResponse.model_validate(user) for user in created_users],
            errors=[],
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to bulk create users: {str(e)}"
        )


# PATCH /admin/sessions/{session_id}/status - Update session status
@router.patch(
    "/sessions/{session_id}/status",
    response_model=AdminSessionStatusResponse,
    status_code=status.HTTP_200_OK,
)
def update_session_status(
    session_id: str,
    payload: SessionStatusUpdate,
    request: Request,
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session '{session_id}' not found."
        )

    previous_status = (
        session_obj.status.value
        if hasattr(session_obj.status, "value")
        else str(session_obj.status)
    )
    session_obj.status = payload.status
    add_audit_log(
        db, request, "session_updated",
        user_id=str(admin_user.get("id")), resource_type="session", resource_id=session_obj.id,
        details=f"status={payload.status.value}",
    )
    db.commit()
    return {
        "id": session_obj.id,
        "name": session_obj.name,
        "status": session_obj.status,
        "message": (
            f"Session status changed from '{previous_status}' "
            f"to '{payload.status.value}'"
        ),
    }


# POST /admin/enrollments/ - Admin enrollment creation
@router.post("/enrollments/", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment(
    payload: EnrollmentCreate,
    request: Request,
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: Session = Depends(get_db)
):
    enrollment = EnrollmentModel(
        id=str(uuid.uuid4()),
        course_id=payload.course_id,
        student_id=payload.user_id,
        is_active=True,
    )

    try:
        db.add(enrollment)
        add_audit_log(
            db, request, "enrollment_added",
            user_id=str(admin_user.get("id")), resource_type="enrollment", resource_id=enrollment.id,
            details=f"course_id={enrollment.course_id}; student_id={enrollment.student_id}",
        )
        db.commit()
        db.refresh(enrollment)
        return {
            "id": enrollment.id,
            "course_id": enrollment.course_id,
            "student_id": enrollment.student_id,
            "is_active": enrollment.is_active,
            "enrolled_at": enrollment.enrolled_at,
        }
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create enrollment: {str(e)}"
        )
