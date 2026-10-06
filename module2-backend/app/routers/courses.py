import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import Column, String, Text, Boolean, Float, DateTime, ForeignKey, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
import os
from dotenv import load_dotenv
from models import CourseModel as Course, UserModel as User

from app.security import get_current_user, require_roles

# 1: Database Setup ---
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

#2. Pydantic Schemas ---
class CourseCreate(BaseModel):
    code: str
    name: str
    description: Optional[str] = None
    semester: str
    instructor_id: str
    venue_name: Optional[str] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    geofence_radius_meters: Optional[float] = 100.0
    require_face_recognition: Optional[bool] = False
    require_device_binding: Optional[bool] = True
    risk_threshold: Optional[float] = 0.5

class CourseListItemResponse(BaseModel):
    id: str
    code: str
    name: str
    semester: str
    instructor_id: str
    instructor_name: str
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
    instructor_id: str
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
# 4. API Endpoints Implementation
# -----------------------------------------------------------------------------
router = APIRouter(prefix="/courses", tags=["courses"])


# GET /courses/ - List courses with optional filters and wrapped pagination response
@router.get("/", response_model=CoursePaginatedResponse, status_code=status.HTTP_200_OK)
def list_courses(
    is_active: Optional[bool] = Query(True, description="Filter by active status"),
    semester: Optional[str] = Query(None, description="Filter by semester"),
    instructor_id: Optional[str] = Query(None, description="Filter by instructor (admin only)"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Course)

    if is_active is not None:
        query = query.filter(Course.is_active == is_active)

    if semester:
        query = query.filter(Course.semester == semester)

    if instructor_id:
        if current_user.get("role") != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Filtering by instructor_id is restricted to administrators."
            )
        query = query.filter(Course.instructor_id == instructor_id)

    total = query.count()
    courses = query.offset(offset).limit(limit).all()

    items = [
        CourseListItemResponse(
            id=course.id,
            code=course.code,
            name=course.name,
            semester=course.semester,
            instructor_id=course.instructor_id,
            instructor_name=course.instructor.full_name if course.instructor else "Unknown",
            venue_name=course.venue_name,
            venue_latitude=course.venue_latitude,
            venue_longitude=course.venue_longitude,
            geofence_radius_meters=course.geofence_radius_meters,
            risk_threshold=course.risk_threshold,
            is_active=course.is_active,
            created_at=course.created_at
        )
        for course in courses
    ]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# POST /courses/ - Create a new course (Admin only)
@router.post("/", response_model=CourseResponse, status_code=status.HTTP_201_CREATED)
def create_course(
    payload: CourseCreate,
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    existing = db.query(Course).filter(Course.code == payload.code).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Course with code '{payload.code}' already exists."
        )

    instructor = db.query(User).filter(User.id == payload.instructor_id).first()
    if not instructor:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Instructor with ID '{payload.instructor_id}' not found."
        )

    course = Course(**payload.model_dump())
    db.add(course)

    try:
        db.commit()
        db.refresh(course)
        return course
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
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )
    return course


# PUT /courses/{course_id} - Update course (Admin or Course Instructor)
@router.put("/{course_id}", response_model=CourseResponse, status_code=status.HTTP_200_OK)
def update_course_full_or_partial(
    course_id: str,
    payload: CourseUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )

    # Permission check: must be admin or the assigned course instructor
    is_admin = current_user.get("role") == "admin"
    is_course_instructor = current_user.get("id") == course.instructor_id

    if not (is_admin or is_course_instructor):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions. Only administrators or the assigned course instructor can update this course."
        )

    # Partial update supported via exclude_unset=True
    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(course, key, value)

    try:
        db.commit()
        db.refresh(course)
        return course
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update course: {str(e)}"
        )


# DELETE /courses/{course_id} - Soft-delete a course (Admin only)
@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def soft_delete_course(
    course_id: str,
    _admin: Dict[str, Any] = Depends(require_roles("admin")),
    db: Session = Depends(get_db)
):
    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )

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