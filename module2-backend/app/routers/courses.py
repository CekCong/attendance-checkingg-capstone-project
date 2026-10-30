import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import Column, String, Text, Boolean, Float, DateTime, ForeignKey, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
import os
from dotenv import load_dotenv
from ..models import CourseModel as Course, UserModel as User, SessionModel, CourseInstructorModel
from ..database import get_db
from ..course_access import require_course_staff_access, staff_course_ids

from app.security import get_current_user, get_optional_current_user, require_roles
from app.audit import add_audit_log

# 1: Database Setup ---
load_dotenv()

Base = declarative_base()


#2. Pydantic Schemas ---
class CourseCreate(BaseModel):
    code: str = Field(min_length=1, max_length=20)
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    semester: str = Field(min_length=1, max_length=20)
    instructor_id: Optional[str] = None
    venue_name: Optional[str] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    geofence_radius_meters: Optional[float] = 100.0
    require_face_recognition: Optional[bool] = False
    require_device_binding: Optional[bool] = True
    risk_threshold: Optional[float] = 0.5

    @field_validator("code", "name", "semester", mode="before")
    @classmethod
    def trim_required_fields(cls, value):
        return value.strip() if isinstance(value, str) else value

class CourseListItemResponse(BaseModel):
    id: str
    code: str
    name: str
    semester: str
    instructor_id: Optional[str] = None
    instructor_name: Optional[str] = None
    venue_name: Optional[str] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    geofence_radius_meters: Optional[float] = 100.0
    risk_threshold: Optional[float] = 0.5
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True

class CoursePaginatedResponse(BaseModel):
    items: List[CourseListItemResponse]
    total: int
    limit: int
    offset: int

class CourseResponse(BaseModel):
    id: str
    code: str
    name: str
    description: Optional[str] = None
    semester: str
    instructor_id: Optional[str] = None
    is_active: bool
    venue_name: Optional[str] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    geofence_radius_meters: Optional[float] = 100.0
    require_face_recognition: Optional[bool] = False
    require_device_binding: Optional[bool] = True
    risk_threshold: Optional[float] = 0.5
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class CourseUpdate(BaseModel):
    code: Optional[str] = None
    name: Optional[str] = None
    description: Optional[str] = None
    semester: Optional[str] = None
    instructor_id: Optional[str] = None
    is_active: Optional[bool] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_face_recognition: Optional[bool] = None
    require_device_binding: Optional[bool] = None
    risk_threshold: Optional[float] = None

# -----------------------------------------------------------------------------
# API Endpoints Implementation

router = APIRouter(prefix="/courses", tags=["courses"])


def course_instructor(db: Session, course_id: str):
    instructor = (
        db.query(User).join(CourseInstructorModel, CourseInstructorModel.instructor_id == User.id)
        .filter(CourseInstructorModel.course_id == course_id).first()
    )
    if not instructor:
        # Existing courses may have assignments only through their sessions.
        instructor = (
            db.query(User).join(SessionModel, SessionModel.instructor_id == User.id)
            .filter(SessionModel.course_id == course_id).first()
        )
    return (instructor.id, instructor.full_name) if instructor else (None, "Unknown")


# GET /courses/ - List courses with optional filters and wrapped pagination response
@router.get("/", response_model=CoursePaginatedResponse, status_code=status.HTTP_200_OK)
def list_courses(
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    instructor_id: Optional[uuid.UUID] = Query(None, description="Filter by instructor (admin only)"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_current_user),
    db: Session = Depends(get_db)
):
    """
    List courses with optional filters. Authentication is optional.
    """
    query = db.query(Course)
    if current_user and current_user.get("role") in {"instructor", "ta"}:
        query = query.filter(Course.id.in_(staff_course_ids(db, current_user)))

    if is_active is not None:
        query = query.filter(Course.is_active == is_active)

    if semester:
        query = query.filter(Course.semester == semester)

    if instructor_id:
        if not current_user or current_user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Filtering by instructor_id is restricted to administrators."
            )
        query = query.filter(Course.id.in_(staff_course_ids(
            db, {"id": str(instructor_id), "role": "instructor"},
        )))

    total = query.count()
    courses = query.order_by(Course.created_at.desc(), Course.id).offset(offset).limit(limit).all()

    items = []
    for course in courses:
        inst_id, inst_name = course_instructor(db, course.id)

        items.append(
            CourseListItemResponse(
                id=course.id,
                code=course.code,
                name=course.name,
                semester=course.semester,
                instructor_id=inst_id,
                instructor_name=inst_name,
                venue_name=course.venue_name,
                venue_latitude=course.venue_latitude,
                venue_longitude=course.venue_longitude,
                geofence_radius_meters=course.geofence_radius_meters,
                risk_threshold=course.risk_threshold,
                is_active=course.is_active,
                created_at=course.created_at,
                updated_at=course.updated_at,
            )
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# POST /courses/ - Create a new course (Admin or Instructor)
@router.post("/", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    current_user: Dict[str, Any] = Depends(require_roles("admin", "instructor")),
    db: Session = Depends(get_db)
):
    """
    Create a course. Instructors can only assign new courses to themselves.
    """
    existing = db.query(Course).filter(Course.code == payload.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Course with code '{payload.code}' already exists."
        )

    instructor_id = payload.instructor_id
    if current_user["role"] == "instructor":
        if instructor_id and instructor_id != current_user["id"]:
            raise HTTPException(status_code=403, detail="Tutors can only create courses assigned to themselves.")
        instructor_id = current_user["id"]

    # Verify instructor exists if provided
    if instructor_id:
        instructor = db.query(User).filter(User.id == instructor_id).first()
        if not instructor or instructor.role != "instructor":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Valid instructor with ID '{instructor_id}' not found."
            )

    # Extract fields excluding instructor_id since Course doesn't store it directly
    course_data = payload.model_dump(exclude={"instructor_id"})

    # Course.id is String(36), requiring an explicit UUID string
    course = Course(
        id=str(uuid.uuid4()),
        **course_data
    )
    db.add(course)

    try:
        db.flush()
        db.refresh(course)

        if instructor_id:
            db.add(CourseInstructorModel(course_id=course.id, instructor_id=instructor_id))

        db.commit()
        db.refresh(course)

        result = CourseResponse.model_validate(course)
        result.instructor_id = instructor_id
        return result
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to create course: {str(e)}"
        )


# GET /courses/{course_id} - Course details (Requires auth)
@router.get("/{course_id}", response_model=CourseResponse, status_code=status.HTTP_200_OK)
def get_course_details(
    course_id: str,
    _current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get course details. **Requires auth.**
    """
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )
    if _current_user.get("role") in {"instructor", "ta"}:
        require_course_staff_access(db, _current_user, course_id)

    inst_id, inst_name = course_instructor(db, course.id)

    return CourseResponse(
        id=course.id,
        code=course.code,
        name=course.name,
        description=course.description,
        semester=course.semester,
        instructor_id=inst_id,
        instructor_name=inst_name,
        venue_name=course.venue_name,
        venue_latitude=course.venue_latitude,
        venue_longitude=course.venue_longitude,
        geofence_radius_meters=course.geofence_radius_meters,
        require_face_recognition=course.require_face_recognition,
        require_device_binding=course.require_device_binding,
        risk_threshold=course.risk_threshold,
        is_active=course.is_active,
        created_at=course.created_at,
        updated_at=course.updated_at,
    )


# PUT /courses/{course_id} - Update course (Admin or Course Instructor)
@router.put("/{course_id}", response_model=CourseResponse, status_code=status.HTTP_200_OK)
def update_course_full_or_partial(
    course_id: str,
    payload: CourseUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update a course. **Requires auth (admin or course instructor).**
    """
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )

    # Check if user is admin
    is_admin = current_user.get("role") == "admin"

    is_course_instructor = (
        current_user.get("role") == "instructor"
        and course_id in staff_course_ids(db, current_user)
    )

    if not (is_admin or is_course_instructor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only administrators or the assigned course instructor can update this course."
        )

    # Extract update data, excluding instructor_id if handled separately
    update_data = payload.model_dump(exclude_unset=True, exclude={"instructor_id"})
    for key, value in update_data.items():
        setattr(course, key, value)

    try:
        db.commit()
        db.refresh(course)

        inst_id, inst_name = course_instructor(db, course.id)

        return CourseResponse(
            id=course.id,
            code=course.code,
            name=course.name,
            description=course.description,
            semester=course.semester,
            instructor_id=inst_id,
            instructor_name=inst_name,
            venue_name=course.venue_name,
            venue_latitude=course.venue_latitude,
            venue_longitude=course.venue_longitude,
            geofence_radius_meters=course.geofence_radius_meters,
            require_face_recognition=course.require_face_recognition,
            require_device_binding=course.require_device_binding,
            risk_threshold=course.risk_threshold,
            is_active=course.is_active,
            created_at=course.created_at,
            updated_at=course.updated_at,
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update course: {str(e)}"
        )


# DELETE /courses/{course_id} - Archive by default; explicitly delete all with permanent=true.
@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_course(
    course_id: str,
    request: Request,
    permanent: bool = Query(False),
    current_user: Dict[str, Any] = Depends(require_roles("admin", "instructor")),
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )

    require_course_staff_access(db, current_user, course_id)
    if current_user["role"] != "admin":
        assignment = db.get(CourseInstructorModel, course_id)
        if assignment and assignment.instructor_id != current_user["id"]:
            raise HTTPException(403, "Only the assigned course tutor can delete this course.")
        if not assignment and db.query(SessionModel.id).filter(
            SessionModel.course_id == course_id,
            SessionModel.instructor_id != current_user["id"],
        ).first():
            raise HTTPException(403, "Ask an administrator to delete a course shared by multiple tutors.")

    if permanent:
        # Database foreign keys cascade to sessions, check-ins, risk signals,
        # enrollments, recurrence links and tutor assignment in this transaction.
        for lesson in db.query(SessionModel).filter(SessionModel.course_id == course_id).all():
            add_audit_log(db, request, "session_deleted", user_id=current_user["id"],
                          resource_type="session", resource_id=lesson.id,
                          details=f"Deleted with course {course.code} ({course_id})")
        db.delete(course)
    else:
        course.is_active = False

    try:
        db.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to delete course: {str(e)}"
        )
