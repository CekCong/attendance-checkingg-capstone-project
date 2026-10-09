import uuid
import os
import math
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy import Column, String, Float, Boolean, DateTime, JSON, ForeignKey, Enum as SQLEnum, create_engine, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
from dotenv import load_dotenv
import enum



from security import get_current_user

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

# --- Enums ---
class CheckinStatus(str, enum.Enum):
    pending = "pending"
    approved = "approved"
    flagged = "flagged"
    rejected = "rejected"
    appealed = "appealed"

class SessionStatus(str, enum.Enum):
    scheduled = "scheduled"
    active = "active"
    closed = "closed"
    cancelled = "cancelled"

class ReviewStatus(str, enum.Enum):
    approved = "approved"
    rejected = "rejected"

# --- SQLAlchemy Models ---
class Course(Base):
    __tablename__ = "courses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(50), nullable=False)
    name = Column(String(255), nullable=False)

from models import SessionModel, UserModel as User

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    status = Column(String(50), nullable=False)
    checked_in_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_accuracy_meters = Column(Float, nullable=True)
    device_fingerprint = Column(String(255), nullable=True)
    distance_from_venue_meters = Column(Float, nullable=True)
    liveness_passed = Column(Boolean, nullable=True)
    liveness_score = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=False, default=0.0)
    risk_factors = Column(JSON, nullable=True, default=list)
    appeal_reason = Column(String, nullable=True)
    appealed_at = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = Column(DateTime(timezone=True), nullable=True)
    review_notes = Column(String, nullable=True)

    session = relationship("SessionModel", backref="attendance_records")
    student = relationship("User", foreign_keys=[student_id], backref="attendance_records")
    reviewer = relationship("User", foreign_keys=[reviewed_by_id])

# --- Helper Functions ---
def calculate_haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (math.sin(delta_phi / 2.0) ** 2 +
         math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    
    return round(R * c, 2)

# --- Pydantic Schemas ---
class CheckinCreate(BaseModel):
    session_id: uuid.UUID
    latitude: float
    longitude: float
    location_accuracy_meters: float
    device_fingerprint: str
    liveness_challenge_response: Optional[str] = None
    qr_code: Optional[str] = None

class RiskFactor(BaseModel):
    type: str
    severity: Optional[str] = None
    weight: float

class CheckinResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    student_id: uuid.UUID
    status: CheckinStatus
    checked_in_at: datetime
    latitude: float
    longitude: float
    distance_from_venue_meters: Optional[float] = None
    liveness_passed: Optional[bool] = None
    liveness_score: Optional[float] = None
    risk_score: float
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    appeal_reason: Optional[str] = None
    appealed_at: Optional[datetime] = None
    reviewed_by_id: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

class CheckinListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    session_name: str
    student_id: uuid.UUID
    student_name: str
    student_email: str
    status: CheckinStatus
    checked_in_at: datetime
    distance_from_venue_meters: Optional[float] = None
    risk_score: float
    liveness_passed: Optional[bool] = None

class CheckinPaginatedResponse(BaseModel):
    items: List[CheckinListItem]
    total: int
    limit: int
    offset: int

class MyCheckinItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    session_name: str
    course_code: str
    status: CheckinStatus
    checked_in_at: datetime
    risk_score: float

class FlaggedCheckinItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    session_name: str
    student_id: uuid.UUID
    student_name: str
    status: CheckinStatus
    checked_in_at: datetime
    risk_score: float
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    appeal_reason: Optional[str] = None
    appealed_at: Optional[datetime] = None

class AppealCreate(BaseModel):
    appeal_reason: str

class AppealResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: CheckinStatus
    appeal_reason: str
    appealed_at: datetime

class ReviewCreate(BaseModel):
    status: ReviewStatus
    review_notes: Optional[str] = None

class ReviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: CheckinStatus
    reviewed_by_id: uuid.UUID
    reviewed_at: datetime
    review_notes: Optional[str] = None

# --- Router ---
router = APIRouter(prefix="/checkins", tags=["Check-ins"])

# GET /checkins/flagged - Get check-ins requiring review (flagged or appealed)
@router.get("/flagged", response_model=List[FlaggedCheckinItem], status_code=status.HTTP_200_OK)
def get_flagged_checkins(
    course_id: Optional[uuid.UUID] = Query(None, description="Filter by course"),
    session_id: Optional[uuid.UUID] = Query(None, description="Filter by session"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "ta", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or TA permissions required."
        )

    query = (
        db.query(AttendanceRecord)
        .join(AttendanceRecord.session)
        .join(AttendanceRecord.student)
        .filter(AttendanceRecord.status.in_([CheckinStatus.flagged.value, CheckinStatus.appealed.value]))
    )

    if course_id:
        query = query.filter(SessionModel.course_id == course_id)
    if session_id:
        query = query.filter(AttendanceRecord.session_id == session_id)

    records = query.order_by(AttendanceRecord.checked_in_at.desc()).limit(limit).all()

    return [
        FlaggedCheckinItem(
            id=rec.id,
            session_id=rec.session_id,
            session_name=rec.session.name if rec.session else "",
            student_id=rec.student_id,
            student_name=rec.student.full_name if rec.student else "",
            status=CheckinStatus(rec.status),
            checked_in_at=rec.checked_in_at,
            risk_score=rec.risk_score,
            risk_factors=rec.risk_factors or [],
            appeal_reason=rec.appeal_reason,
            appealed_at=rec.appealed_at
        )
        for rec in records
    ]

# GET /checkins/my-checkins - Get current student's check-in history
@router.get("/my-checkins", response_model=List[MyCheckinItem], status_code=status.HTTP_200_OK)
def get_my_checkins(
    course_id: Optional[uuid.UUID] = Query(None, description="Filter by course"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only students can access their check-in history."
        )

    student_id = uuid.UUID(str(current_user.get("id")))

    query = (
        db.query(AttendanceRecord)
        .join(AttendanceRecord.session)
        .outerjoin(SessionModel.course)
        .filter(AttendanceRecord.student_id == student_id)
    )

    if course_id:
        query = query.filter(SessionModel.course_id == course_id)

    records = query.order_by(AttendanceRecord.checked_in_at.desc()).limit(limit).all()

    return [
        MyCheckinItem(
            id=rec.id,
            session_id=rec.session_id,
            session_name=rec.session.name if rec.session else "",
            course_code=rec.session.course.code if rec.session and rec.session.course else "",
            status=CheckinStatus(rec.status),
            checked_in_at=rec.checked_in_at,
            risk_score=rec.risk_score
        )
        for rec in records
    ]

# GET /checkins/{checkin_id} - Get specific check-in details
@router.get("/{checkin_id}", response_model=CheckinResponse, status_code=status.HTTP_200_OK)
def get_checkin_detail(
    checkin_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == checkin_id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in with ID '{checkin_id}' not found."
        )

    user_id = uuid.UUID(str(current_user.get("id")))
    user_role = current_user.get("role")

    is_owner = record.student_id == user_id
    is_staff = user_role in ["instructor", "ta", "admin"]

    if not (is_owner or is_staff):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to view this check-in."
        )

    return record

# POST /checkins/{id}/appeal - Appeal a rejected/flagged check-in
@router.post("/{id}/appeal", response_model=AppealResponse, status_code=status.HTTP_200_OK)
def appeal_checkin(
    id: uuid.UUID,
    payload: AppealCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only students can appeal check-ins."
        )

    student_id = uuid.UUID(str(current_user.get("id")))
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == id).first()

    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in with ID '{id}' not found."
        )

    if record.student_id != student_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You can only appeal your own check-ins."
        )

    if record.status not in [CheckinStatus.rejected.value, CheckinStatus.flagged.value]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot appeal a check-in with status '{record.status}'. Only rejected or flagged check-ins can be appealed."
        )

    if record.status == CheckinStatus.appealed.value or record.appeal_reason is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This check-in has already been appealed."
        )

    now = datetime.now(timezone.utc)
    if record.checked_in_at:
        checkin_time = record.checked_in_at
        if checkin_time.tzinfo is None:
            checkin_time = checkin_time.replace(tzinfo=timezone.utc)
            
        if now > (checkin_time + timedelta(days=7)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The appeal window has expired (7 days from check-in)."
            )

    record.status = CheckinStatus.appealed.value
    record.appeal_reason = payload.appeal_reason
    record.appealed_at = now

    db.commit()
    db.refresh(record)

    return record

# POST /checkins/{id}/review - Review a flagged/appealed check-in
@router.post("/{id}/review", response_model=ReviewResponse, status_code=status.HTTP_200_OK)
def review_checkin(
    id: uuid.UUID,
    payload: ReviewCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    reviewer_role = current_user.get("role")
    if reviewer_role not in ["instructor", "ta", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only instructors, TAs, or admins can review check-ins."
        )

    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == id).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in with ID '{id}' not found."
        )

    reviewer_id = uuid.UUID(str(current_user.get("id")))
    now = datetime.now(timezone.utc)

    record.status = payload.status.value
    record.reviewed_by_id = reviewer_id
    record.reviewed_at = now
    record.review_notes = payload.review_notes

    db.commit()
    db.refresh(record)

    return record

# GET /checkins/ - List all check-ins with filters (instructor/admin only)
@router.get("/", response_model=CheckinPaginatedResponse, status_code=status.HTTP_200_OK)
def list_checkins(
    session_id: Optional[uuid.UUID] = Query(None, description="Filter by session"),
    course_id: Optional[uuid.UUID] = Query(None, description="Filter by course"),
    student_id: Optional[uuid.UUID] = Query(None, description="Filter by student"),
    status_filter: Optional[CheckinStatus] = Query(None, alias="status", description="Filter by status"),
    min_risk_score: Optional[float] = Query(None, description="Minimum risk score"),
    max_risk_score: Optional[float] = Query(None, description="Maximum risk score"),
    start_date: Optional[datetime] = Query(None, description="Check-ins after this date"),
    end_date: Optional[datetime] = Query(None, description="Check-ins before this date"),
    limit: int = Query(50, ge=1, le=100, description="Results per page"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or admin permissions required."
        )

    query = db.query(AttendanceRecord).join(AttendanceRecord.session).join(AttendanceRecord.student)

    if session_id:
        query = query.filter(AttendanceRecord.session_id == session_id)
    if course_id:
        query = query.filter(SessionModel.course_id == course_id)
    if student_id:
        query = query.filter(AttendanceRecord.student_id == student_id)
    if status_filter:
        query = query.filter(AttendanceRecord.status == status_filter.value)
    if min_risk_score is not None:
        query = query.filter(AttendanceRecord.risk_score >= min_risk_score)
    if max_risk_score is not None:
        query = query.filter(AttendanceRecord.risk_score <= max_risk_score)
    if start_date:
        query = query.filter(AttendanceRecord.checked_in_at >= start_date)
    if end_date:
        query = query.filter(AttendanceRecord.checked_in_at <= end_date)

    total = query.count()
    records = query.order_by(AttendanceRecord.checked_in_at.desc()).offset(offset).limit(limit).all()

    items = [
        CheckinListItem(
            id=rec.id,
            session_id=rec.session_id,
            session_name=rec.session.name if rec.session else "",
            student_id=rec.student_id,
            student_name=rec.student.full_name if rec.student else "",
            student_email=rec.student.email if rec.student else "",
            status=CheckinStatus(rec.status),
            checked_in_at=rec.checked_in_at,
            distance_from_venue_meters=rec.distance_from_venue_meters,
            risk_score=rec.risk_score,
            liveness_passed=rec.liveness_passed
        )
        for rec in records
    ]

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "offset": offset
    }

# POST /checkins/ - Student check-in to a session
@router.post("/", response_model=CheckinResponse, status_code=status.HTTP_201_CREATED)
def create_checkin(
    payload: CheckinCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only students can perform check-ins."
        )

    student_id = uuid.UUID(str(current_user.get("id")))

    session_obj = db.query(SessionModel).filter(SessionModel.id == payload.session_id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{payload.session_id}' not found."
        )

    if session_obj.status != SessionStatus.active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Session is not currently active."
        )

    now = datetime.now(timezone.utc)

    if now < session_obj.checkin_opens_at or now > session_obj.checkin_closes_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in window is closed for this session."
        )

    existing_checkin = (
        db.query(AttendanceRecord)
        .filter(
            AttendanceRecord.session_id == payload.session_id,
            AttendanceRecord.student_id == student_id
        )
        .first()
    )
    if existing_checkin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Already checked in to this session."
        )

    if session_obj.qr_code_secret:
        if payload.qr_code != session_obj.qr_code_secret:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid QR code provided for this session."
            )
        if session_obj.qr_code_expires_at and now > session_obj.qr_code_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QR code for this session has expired."
            )

    risk_factors = []
    total_risk = 0.0
    distance_meters = None
    geofence_exceeded_critical = False

    if session_obj.venue_latitude is not None and session_obj.venue_longitude is not None:
        distance_meters = calculate_haversine_distance(
            payload.latitude,
            payload.longitude,
            session_obj.venue_latitude,
            session_obj.venue_longitude
        )

        max_radius = session_obj.geofence_radius_meters or 100.0

        if distance_meters > (2 * max_radius):
            geofence_exceeded_critical = True
            risk_factors.append({"type": "critical_geofence_exceeded", "severity": "high", "weight": 1.0})
            total_risk += 1.0
        elif distance_meters > max_radius:
            risk_factors.append({"type": "geo_out_of_bounds", "severity": "high", "weight": 0.40})
            total_risk += 0.40

    liveness_passed = None
    liveness_score = None

    if session_obj.require_liveness_check:
        if not payload.liveness_challenge_response:
            liveness_passed = False
            liveness_score = 0.0
            risk_factors.append({"type": "liveness_failed", "severity": "high", "weight": 1.0})
            total_risk += 1.0
        else:
            liveness_passed = True
            liveness_score = 0.92

    if payload.device_fingerprint == "unknown_device":
        risk_factors.append({"type": "device_unknown", "severity": "medium", "weight": 0.15})
        total_risk += 0.15

    total_risk = round(min(total_risk, 1.0), 2)

    if liveness_passed is False or geofence_exceeded_critical:
        checkin_status = CheckinStatus.rejected
    else:
        threshold = session_obj.risk_threshold or 0.50
        if total_risk >= threshold:
            checkin_status = CheckinStatus.flagged
        else:
            checkin_status = CheckinStatus.approved

    new_record = AttendanceRecord(
        id=uuid.uuid4(),
        session_id=payload.session_id,
        student_id=student_id,
        status=checkin_status.value,
        checked_in_at=now,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_accuracy_meters=payload.location_accuracy_meters,
        device_fingerprint=payload.device_fingerprint,
        distance_from_venue_meters=distance_meters,
        liveness_passed=liveness_passed,
        liveness_score=liveness_score,
        risk_score=total_risk,
        risk_factors=risk_factors
    )

    db.add(new_record)
    db.commit()
    db.refresh(new_record)

    return new_record