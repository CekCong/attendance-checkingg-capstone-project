import uuid
import html
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, StrictBool, field_validator
from sqlalchemy import or_
from sqlalchemy.orm import Session
import enum

from ..database import get_db
from ..models import EnrollmentModel, UserModel as User
from ..security import get_current_user, require_roles, revoke_user_sessions
from ..retention import ACCOUNT_RETENTION_DAYS
from ..course_access import staff_course_ids
from ..services.face_client import FaceServiceError, enroll_face as enroll_face_with_service
from ..audit import add_audit_log
from ..roster import link_matriculation, normalize_matriculation
from ..services.face_client import check_camera_readiness
from ..rate_limit import enforce_rate_limit

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
    matriculation_number: Optional[str] = None

    @field_validator("matriculation_number")
    @classmethod
    def validate_number(cls, value):
        return normalize_matriculation(value)

    @field_validator("full_name")
    @classmethod
    def escape_full_name(cls, value: Optional[str]) -> Optional[str]:
        return html.escape(value, quote=False) if value is not None else None

class AdminUpdateUserBody(BaseModel):
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None

# Request schema for POST /users/me/face/enroll
class FaceEnrollBody(BaseModel):
    image: str = Field(..., description="Base64-encoded face image (PNG/JPEG), without data URL prefix")


class CameraReadinessBody(BaseModel):
    image: str = Field(..., min_length=1, max_length=2_000_000)


class CameraReadinessResponse(BaseModel):
    ready: StrictBool
    message: str
    warnings: List[str] = Field(default_factory=list)

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
    matriculation_number: Optional[str] = None
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



async def process_face_enrollment(
    image_base64: str,
    user_id: str,
    camera_consent: bool,
) -> tuple[str, float]:
    try:
        result = await enroll_face_with_service(
            user_id=user_id,
            image=image_base64,
            camera_consent=camera_consent,
        )
        if not result.get("enrollment_successful"):
            raise FaceServiceError(400, "Face image could not be enrolled")
        return str(result["face_template_hash"]), float(result["quality_score"])
    except FaceServiceError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
        ) from exc
    except (KeyError, TypeError, ValueError) as exc:
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


class DeleteMeBody(BaseModel):
    current_password: str = Field(min_length=1)


@router.delete("/me", status_code=202)
def schedule_account_deletion(
    body: DeleteMeBody, request: Request,
    current_user=Depends(get_current_user), db: Session = Depends(get_db),
):
    from .auth import verify_password
    from ..rate_limit import enforce_rate_limit
    user = db.query(User).filter(User.id == current_user["id"]).one()
    enforce_rate_limit(f"delete-account:{user.id}", 10, 3600)
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(400, "Current password is incorrect")
    user.scheduled_deletion_at = datetime.utcnow() + timedelta(days=ACCOUNT_RETENTION_DAYS)
    user.is_active = False
    revoke_user_sessions(db, user.id)
    add_audit_log(db, request, "user_updated", user_id=user.id, resource_type="user",
                  resource_id=user.id, details="Account deletion scheduled")
    db.commit()
    return {"scheduled_deletion_at": user.scheduled_deletion_at, "message": "Account disabled; personal data is scheduled for erasure after 30 days."}


# PUT /users/me
@router.put("/me", response_model=UserResponse)
def update_me(
    body: UpdateMeBody,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == current_user.get("id")).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    updated_fields = list(update_data)
    if "matriculation_number" in update_data:
        link_matriculation(db, request, user, update_data.pop("matriculation_number"))
    if update_data.get("camera_consent") is False:
        user.face_embedding_hash = None
        user.face_enrolled = False
    if "full_name" in update_data and update_data["full_name"]:
        update_data["full_name"] = update_data["full_name"].strip()

    for field, value in update_data.items():
        setattr(user, field, value)

    add_audit_log(
        db, request, "user_updated",
        user_id=user.id, resource_type="user", resource_id=user.id,
        details=f"updated_fields={','.join(updated_fields)}",
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/me/face/readiness", response_model=CameraReadinessResponse)
async def camera_readiness(
    body: CameraReadinessBody,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == current_user.get("id")).first()
    if not user:
        raise HTTPException(404, "User not found")
    if not user.camera_consent:
        raise HTTPException(400, "Camera consent not given")
    enforce_rate_limit(f"camera-readiness:{user.id}", limit=20, window=60)
    try:
        return CameraReadinessResponse(**await check_camera_readiness(body.image))
    except FaceServiceError as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(503, "Camera readiness service returned an invalid response") from exc


# POST /users/me/face/enroll
@router.post("/me/face/enroll", response_model=FaceEnrollResponse)
async def enroll_face(
    body: FaceEnrollBody,
    request: Request,
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

    embedding_hash, quality_score = await process_face_enrollment(
        body.image,
        str(user.id),
        user.camera_consent,
    )

    # Update database record upon successful processing
    user.face_embedding_hash = embedding_hash
    user.face_enrolled = True

    add_audit_log(
        db, request, "face_enrolled",
        user_id=user.id, resource_type="user", resource_id=user.id,
    )
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

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    is_self = str(current_user.get("id")) == user_id
    if current_role != "admin" and not is_self:
        allowed = False
        if current_role in {"instructor", "ta"} and user.role == "student":
            allowed_courses = staff_course_ids(db, current_user)
            allowed = bool(allowed_courses) and db.query(EnrollmentModel).filter(
                EnrollmentModel.student_id == user_id,
                EnrollmentModel.course_id.in_(allowed_courses),
                EnrollmentModel.is_active.is_(True),
            ).first() is not None
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions"
            )

    return user


# PATCH /users/{user_id}
@router.patch("/{user_id}", response_model=UserResponse)
def update_user_details(
    user_id: str,
    body: AdminUpdateUserBody,
    request: Request,
    admin_user: Dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    update_data = body.model_dump(exclude_unset=True)
    if update_data.get("is_active") and (user.scheduled_deletion_at is not None or user.hashed_password == "!deleted"):
        raise HTTPException(409, "Accounts scheduled for deletion or erased cannot be activated.")
    if update_data.get("is_active") is False:
        revoke_user_sessions(db, user.id)
    for field, value in update_data.items():
        setattr(user, field, value)

    add_audit_log(
        db, request, "user_updated",
        user_id=str(admin_user.get("id")), resource_type="user", resource_id=user.id,
        details=f"updated_fields={','.join(update_data.keys())}",
    )
    db.commit()
    db.refresh(user)
    return user
