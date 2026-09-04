import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import Column, String, Text, Boolean, Float, DateTime, Enum as SQLEnum, ForeignKey, create_engine, func
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import enum

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

# --- Enums & SQLAlchemy Model ---
class SessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    active = "active"
    closed = "closed"
    cancelled = "cancelled"

class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    course_id = Column(String(36), ForeignKey("courses.id", ondelete="CASCADE"), nullable=False)
    instructor_id = Column(String(36), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    session_type = Column(String(50), default="lecture")
    description = Column(Text, nullable=True)
    scheduled_start = Column(DateTime, nullable=False)
    scheduled_end = Column(DateTime, nullable=False)
    checkin_opens_at = Column(DateTime, nullable=False)
    checkin_closes_at = Column(DateTime, nullable=False)
    status = Column(SQLEnum(SessionStatus), nullable=False)
    actual_start = Column(DateTime, nullable=True)
    actual_end = Column(DateTime, nullable=True)
    venue_latitude = Column(Float, nullable=True)
    venue_longitude = Column(Float, nullable=True)
    venue_name = Column(String(255), nullable=True)
    geofence_radius_meters = Column(Float, nullable=True)
    require_liveness_check = Column(Boolean, default=True)
    require_face_match = Column(Boolean, default=False)
    risk_threshold = Column(Float, nullable=True)
    qr_code_secret = Column(String(64), nullable=True)
    qr_code_expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

# --- Pydantic Schemas ---
class SessionCreate(BaseModel):
    course_id: str
    name: str
    scheduled_start: datetime
    scheduled_end: datetime
    checkin_opens_at: datetime
    checkin_closes_at: datetime
    status: SessionStatus = SessionStatus.scheduled
    session_type: Optional[str] = "lecture"
    description: Optional[str] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_liveness_check: Optional[bool] = True
    require_face_match: Optional[bool] = False
    risk_threshold: Optional[float] = None

class SessionUpdate(BaseModel):
    name: Optional[str] = None
    session_type: Optional[str] = None
    description: Optional[str] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    checkin_opens_at: Optional[datetime] = None
    checkin_closes_at: Optional[datetime] = None
    status: Optional[SessionStatus] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_liveness_check: Optional[bool] = None
    require_face_match: Optional[bool] = None
    risk_threshold: Optional[float] = None
    qr_code_secret: Optional[str] = None
    qr_code_expires_at: Optional[datetime] = None

class SessionResponse(BaseModel):
    id: str
    course_id: str
    instructor_id: Optional[str] = None
    name: str
    session_type: Optional[str] = "lecture"
    description: Optional[str] = None
    scheduled_start: datetime
    scheduled_end: datetime
    checkin_opens_at: datetime
    checkin_closes_at: datetime
    status: SessionStatus
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    venue_latitude: Optional[float] = None
    venue_longitude: Optional[float] = None
    venue_name: Optional[str] = None
    geofence_radius_meters: Optional[float] = None
    require_liveness_check: bool
    require_face_match: bool
    risk_threshold: Optional[float] = None
    qr_code_secret: Optional[str] = None
    qr_code_expires_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# --- Router Implementation (sessions.py) ---
router = APIRouter(prefix="/sessions", tags=["Session Management"])

# POST /sessions - Create session (instructor only)
@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: SessionCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor permissions required."
        )

    new_session = SessionModel(
        id=str(uuid.uuid4()),
        instructor_id=current_user.get("id"),
        **payload.model_dump()
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session


# GET /sessions - List sessions
@router.get("", response_model=List[SessionResponse], status_code=status.HTTP_200_OK)
def list_sessions(
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(10, ge=1, le=100, description="Pagination limit"),
    course_id: Optional[str] = Query(None, description="Filter by course"),
    status_filter: Optional[SessionStatus] = Query(None, alias="status", description="Filter by status"),
    db: Session = Depends(get_db)
):
    query = db.query(SessionModel)
    if course_id:
        query = query.filter(SessionModel.course_id == course_id)
    if status_filter:
        query = query.filter(SessionModel.status == status_filter)

    return query.offset(skip).limit(limit).all()


# GET /sessions/{id} - Session details
@router.get("/{id}", response_model=SessionResponse, status_code=status.HTTP_200_OK)
def get_session_details(id: str, db: Session = Depends(get_db)):
    session_obj = db.query(SessionModel).filter(SessionModel.id == id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{id}' not found."
        )
    return session_obj


# PATCH /sessions/{id} - Update session
@router.patch("/{id}", response_model=SessionResponse, status_code=status.HTTP_200_OK)
def update_session(
    id: str,
    payload: SessionUpdate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    session_obj = db.query(SessionModel).filter(SessionModel.id == id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{id}' not found."
        )

    if current_user.get("role") != "admin" and session_obj.instructor_id != current_user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the session instructor or an admin can modify this session."
        )

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(session_obj, key, value)

    db.commit()
    db.refresh(session_obj)
    return session_obj


# DELETE /sessions/{id} - Delete session
@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(
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

    if current_user.get("role") != "admin" and session_obj.instructor_id != current_user.get("id"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only the session instructor or an admin can delete this session."
        )

    db.delete(session_obj)
    db.commit()