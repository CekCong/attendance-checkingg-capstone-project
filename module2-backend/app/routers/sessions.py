import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import Column, String, Text, Boolean, Float, DateTime, Enum as SQLEnum, ForeignKey, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
import enum
import os
from dotenv import load_dotenv

from app.security import get_current_user
from app.models import CourseModel as Course, SessionModel, EnrollmentModel as CourseEnrollment, CheckinModel as AttendanceRecord, SessionOccurrenceModel
from app.database import get_db
from app.course_access import require_course_staff_access, staff_course_ids
from app.audit import add_audit_log

# --- Database & Base Setup ---
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

class SessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    active = "active"
    closed = "closed"
    cancelled = "cancelled"

# --- Pydantic Schemas ---
class SessionCreate(BaseModel):
    course_id: str
    name: str
    session_type: Optional[str] = Field("lecture", pattern="^(lecture|tutorial|lab|exam)$")
    scheduled_start: datetime
    scheduled_end: datetime
    checkin_opens_at: Optional[datetime] = None
    checkin_closes_at: Optional[datetime] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_liveness_check: Optional[bool] = True
    require_face_match: Optional[bool] = False
    risk_threshold: Optional[float] = None

    @model_validator(mode="after")
    def validate_and_apply_defaults(self):
        now = datetime.now(timezone.utc)
        start_time = self.scheduled_start if self.scheduled_start.tzinfo else self.scheduled_start.replace(tzinfo=timezone.utc)
        if start_time <= now:
            raise ValueError("scheduled_start must be in the future.")

        if self.scheduled_end <= self.scheduled_start:
            raise ValueError("scheduled_end must be after scheduled_start.")

        if self.checkin_opens_at is None:
            self.checkin_opens_at = self.scheduled_start - timedelta(minutes=15)
        if self.checkin_closes_at is None:
            self.checkin_closes_at = self.scheduled_start + timedelta(minutes=30)

        if self.checkin_closes_at <= self.checkin_opens_at:
            raise ValueError("checkin_closes_at must be after checkin_opens_at.")

        return self

class SessionUpdate(BaseModel):
    name: Optional[str] = None
    session_type: Optional[str] = None
    description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    checkin_opens_at: Optional[datetime] = None
    checkin_closes_at: Optional[datetime] = None
    status: Optional[SessionStatus] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_liveness_check: Optional[bool] = None
    require_face_match: Optional[bool] = None
    risk_threshold: Optional[float] = None

class SessionActiveResponse(BaseModel):
    id: str
    course_id: str
    course_code: str
    name: str
    status: SessionStatus
    scheduled_start: datetime
    scheduled_end: datetime
    checkin_opens_at: datetime
    checkin_closes_at: datetime
    venue_name: Optional[str] = None

    class Config:
        from_attributes = True

class SessionListItemResponse(BaseModel):
    id: str
    series_id: Optional[str] = None
    course_id: str
    course_code: str
    course_name: str
    instructor_id: Optional[str] = None
    name: str
    session_type: Optional[str] = "lecture"
    status: SessionStatus
    scheduled_start: datetime
    scheduled_end: datetime
    checkin_opens_at: datetime
    checkin_closes_at: datetime
    venue_name: Optional[str] = None
    total_enrolled: int
    checked_in_count: int

    class Config:
        from_attributes = True

class SessionPaginatedResponse(BaseModel):
    items: List[SessionListItemResponse]
    total: int
    limit: int
    offset: int

class SessionResponse(BaseModel):
    id: str
    course_id: str
    instructor_id: Optional[str] = None
    name: str
    session_type: Optional[str] = "lecture"
    status: SessionStatus
    scheduled_start: datetime
    scheduled_end: datetime
    checkin_opens_at: datetime
    checkin_closes_at: datetime
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_liveness_check: bool
    require_face_match: bool
    risk_threshold: Optional[float] = None
    qr_code_enabled: bool = False
    created_at: datetime

    class Config:
        from_attributes = True

# --- Router Implementation (sessions.py) ---
router = APIRouter(prefix="/sessions", tags=["Session Management"])

# POST /sessions - Create session (instructor only)
@router.post("/", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor permissions required."
        )

    course = db.query(Course).filter(Course.id == payload.course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{payload.course_id}' not found."
        )

    if current_user.get("role") == "instructor":
        require_course_staff_access(db, current_user, course.id)

    session_data = payload.model_dump()

    if session_data.get("venue_name") is None:
        session_data["venue_name"] = course.venue_name
    if session_data.get("venue_latitude") is None:
        session_data["venue_latitude"] = course.venue_latitude
    if session_data.get("venue_longitude") is None:
        session_data["venue_longitude"] = course.venue_longitude
    if session_data.get("geofence_radius_meters") is None:
        session_data["geofence_radius_meters"] = course.geofence_radius_meters
    if session_data.get("risk_threshold") is None:
        session_data["risk_threshold"] = course.risk_threshold

    new_session = SessionModel(
        id=str(uuid.uuid4()),
        instructor_id=current_user.get("id"),
        status=SessionStatus.scheduled,
        **session_data
    )

    db.add(new_session)
    add_audit_log(
        db,
        request,
        "session_created",
        user_id=str(current_user.get("id")),
        resource_type="session",
        resource_id=new_session.id,
        details=f"course_id={new_session.course_id}",
    )
    db.commit()
    db.refresh(new_session)
    
    response = SessionResponse.model_validate(new_session)
    response.qr_code_enabled = bool(new_session.qr_code_secret)
    return response


# GET /sessions/ - List all sessions with filters (instructor/admin only)
@router.get("/", response_model=SessionPaginatedResponse, status_code=status.HTTP_200_OK)
def list_sessions(
    status_filter: Optional[SessionStatus] = Query(None, alias="status", description="Filter by status"),
    course_id: Optional[str] = Query(None, description="Filter by course"),
    instructor_id: Optional[str] = Query(None, description="Filter by instructor"),
    start_date: Optional[datetime] = Query(None, description="Sessions starting after this date"),
    end_date: Optional[datetime] = Query(None, description="Sessions starting before this date"),
    overlap_start: Optional[datetime] = Query(None, description="Sessions ending after this date"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "ta", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor, TA, or admin permissions required."
        )

    query = db.query(SessionModel)
    if current_user.get("role") in {"instructor", "ta"}:
        query = query.filter(SessionModel.course_id.in_(staff_course_ids(db, current_user)))

    if status_filter:
        query = query.filter(SessionModel.status == status_filter)
    if course_id:
        query = query.filter(SessionModel.course_id == course_id)
    if instructor_id:
        query = query.filter(SessionModel.instructor_id == instructor_id)
    if start_date:
        query = query.filter(SessionModel.scheduled_start >= start_date)
    if end_date:
        query = query.filter(SessionModel.scheduled_start < end_date)
    if overlap_start:
        query = query.filter(SessionModel.scheduled_end > overlap_start)

    total = query.count()
    sessions = query.order_by(SessionModel.scheduled_start, SessionModel.id).offset(offset).limit(limit).all()
    series_ids = dict(db.query(SessionOccurrenceModel.session_id, SessionOccurrenceModel.series_id)
                      .filter(SessionOccurrenceModel.session_id.in_([s.id for s in sessions])).all())

    items = []
    for s in sessions:
        total_enrolled = (
            db.query(func.count(CourseEnrollment.id))
            .filter(CourseEnrollment.course_id == s.course_id)
            .scalar() or 0
        )

        checked_in_count = (
            db.query(func.count(AttendanceRecord.id))
            .filter(AttendanceRecord.session_id == s.id)
            .scalar() or 0
        )

        items.append(
            SessionListItemResponse(
                id=s.id,
                series_id=series_ids.get(s.id),
                course_id=s.course_id,
                course_code=s.course.code if s.course else "",
                course_name=s.course.name if s.course else "",
                instructor_id=s.instructor_id,
                name=s.name,
                session_type=s.session_type,
                status=s.status,
                scheduled_start=s.scheduled_start,
                scheduled_end=s.scheduled_end,
                checkin_opens_at=s.checkin_opens_at,
                checkin_closes_at=s.checkin_closes_at,
                venue_name=s.venue_name,
                total_enrolled=total_enrolled,
                checked_in_count=checked_in_count
            )
        )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }


# GET /sessions/active - Public endpoint to list currently active check-in sessions
@router.get("/active", response_model=List[SessionActiveResponse], status_code=status.HTTP_200_OK)
def list_active_sessions(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    sessions = (
        db.query(SessionModel)
        .filter(
            SessionModel.status == SessionStatus.active,
            SessionModel.checkin_opens_at <= now,
            SessionModel.checkin_closes_at >= now
        )
        .all()
    )

    return [
        SessionActiveResponse(
            id=s.id,
            course_id=s.course_id,
            course_code=s.course.code if s.course else "",
            name=s.name,
            status=s.status,
            scheduled_start=s.scheduled_start,
            scheduled_end=s.scheduled_end,
            checkin_opens_at=s.checkin_opens_at,
            checkin_closes_at=s.checkin_closes_at,
            venue_name=s.venue_name
        )
        for s in sessions
    ]


# GET /sessions/my-sessions - List sessions for courses the user teaches or is enrolled in
@router.get("/my-sessions", response_model=List[SessionResponse], status_code=status.HTTP_200_OK)
def list_my_sessions(
    status_filter: Optional[SessionStatus] = Query(None, alias="status", description="Filter by status"),
    upcoming: bool = Query(False, description="Only show future sessions"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_id = current_user.get("id")
    user_role = current_user.get("role")

    query = db.query(SessionModel)

    if user_role == "instructor":
        query = query.filter(SessionModel.instructor_id == user_id)
    elif user_role == "ta":
        query = query.filter(SessionModel.course_id.in_(staff_course_ids(db, current_user)))
    elif user_role == "admin":
        query = query.filter(SessionModel.instructor_id == user_id)
    else:
        enrolled_course_ids = (
            db.query(CourseEnrollment.course_id)
            .filter(
                CourseEnrollment.student_id == user_id,
                CourseEnrollment.is_active.is_(True),
            )
            .subquery()
        )
        query = query.filter(SessionModel.course_id.in_(enrolled_course_ids))

    if status_filter:
        query = query.filter(SessionModel.status == status_filter)

    if upcoming:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        query = query.filter(SessionModel.scheduled_start > now)

    sessions = query.limit(limit).all()
    results = []
    for s in sessions:
        resp = SessionResponse.model_validate(s)
        resp.qr_code_enabled = bool(s.qr_code_secret)
        results.append(resp)
    return results


# GET /sessions/{id} - Session details (Requires auth)
@router.get("/{id}", response_model=SessionResponse, status_code=status.HTTP_200_OK)
def get_session_details(
    id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session_obj = db.query(SessionModel).filter(SessionModel.id == id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{id}' not found."
        )
    if current_user.get("role") in {"instructor", "ta"}:
        require_course_staff_access(db, current_user, session_obj.course_id)
    
    response = SessionResponse.model_validate(session_obj)
    response.qr_code_enabled = bool(session_obj.qr_code_secret)
    return response


# PATCH /sessions/{id} - Update a session (Requires auth: instructor only, session owner)
@router.patch("/{id}", response_model=SessionResponse, status_code=status.HTTP_200_OK)
def update_session(
    id: str,
    payload: SessionUpdate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") != "instructor":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor role required."
        )

    session_obj = db.query(SessionModel).filter(SessionModel.id == id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{id}' not found."
        )

    if session_obj.instructor_id != current_user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only update sessions you own."
        )

    update_data = payload.model_dump(exclude_unset=True)

    if "status" in update_data and update_data["status"] != session_obj.status:
        current_status = session_obj.status
        target_status = update_data["status"]
        now = datetime.now(timezone.utc)

        valid_transition = False

        if current_status == SessionStatus.scheduled and target_status == SessionStatus.active:
            valid_transition = True
            session_obj.actual_start = now
        elif current_status == SessionStatus.active and target_status == SessionStatus.closed:
            valid_transition = True
            session_obj.actual_end = now
        elif target_status == SessionStatus.cancelled:
            valid_transition = True

        if not valid_transition:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status transition from '{current_status.value}' to '{target_status.value}'."
            )

    for key, value in update_data.items():
        setattr(session_obj, key, value)

    add_audit_log(
        db,
        request,
        "session_updated",
        user_id=str(current_user.get("id")),
        resource_type="session",
        resource_id=session_obj.id,
        details=f"updated_fields={','.join(update_data.keys())}",
    )
    db.commit()
    db.refresh(session_obj)

    response = SessionResponse.model_validate(session_obj)
    response.qr_code_enabled = bool(session_obj.qr_code_secret)
    return response


# DELETE /sessions/{id} - Delete a session (Requires auth: instructor only, session owner)
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
    id: str,
    request: Request,
    permanent: bool = Query(False, description="Also delete attendance records, regardless of session status"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Role check: Instructor only
    if current_user.get("role") not in {"instructor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor role required."
        )

    session_obj = db.query(SessionModel).filter(SessionModel.id == id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{id}' not found."
        )

    # Ownership check: Must be the session owner
    if current_user.get("role") != "admin" and session_obj.instructor_id != current_user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only delete sessions you own."
        )

    # Status check: Only 'scheduled' sessions can be deleted
    if not permanent and session_obj.status != SessionStatus.scheduled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot delete session with status '{session_obj.status}'. "
                "Only sessions with status 'scheduled' can be deleted. "
                "Active or closed sessions should be cancelled instead."
            )
        )

    add_audit_log(
        db,
        request,
        "session_deleted",
        user_id=str(current_user.get("id")),
        resource_type="session",
        resource_id=session_obj.id,
        details=f"course_id={session_obj.course_id}",
    )
    db.delete(session_obj)
    db.commit()
