import uuid
import math
import json
import enum
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, ConfigDict, field_validator
from sqlalchemy.orm import Session
from ..security import get_current_user
from ..rate_limit import client_ip
from ..database import get_db as shared_get_db
from ..models import CheckinModel, DeviceModel, SessionModel, UserModel as User
from ..audit import add_audit_log
from ..course_access import require_course_staff_access, staff_course_ids
from ..services.face_client import (
    FaceServiceError,
    assess_risk,
    check_liveness,
    verify_face,
)

AttendanceRecord = CheckinModel

def get_db():
    yield from shared_get_db()

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
    location_accuracy_meters: Optional[float] = None
    device_fingerprint: str
    liveness_challenge_response: Optional[str] = None
    qr_code: Optional[str] = None
    face_image: Optional[str] = None  # Base64-encoded image for liveness check

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
    liveness_challenge_type: Optional[str] = None
    face_match_passed: Optional[bool] = None
    face_match_score: Optional[float] = None
    risk_score: float
    risk_factors: List[RiskFactor] = Field(default_factory=list)
    appeal_reason: Optional[str] = None
    appealed_at: Optional[datetime] = None
    reviewed_by_id: Optional[uuid.UUID] = None
    reviewed_at: Optional[datetime] = None
    review_notes: Optional[str] = None

    @field_validator("risk_factors", mode="before")
    @classmethod
    def parse_risk_factors(cls, value):
        return json.loads(value) if isinstance(value, str) else value or []

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

    @field_validator("risk_factors", mode="before")
    @classmethod
    def parse_risk_factors(cls, value):
        return json.loads(value) if isinstance(value, str) else value or []

class FlaggedCheckinPaginatedResponse(BaseModel):
    items: List[FlaggedCheckinItem]
    total: int

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
@router.get("/flagged", response_model=FlaggedCheckinPaginatedResponse, status_code=status.HTTP_200_OK)
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
    if current_user.get("role") in {"instructor", "ta"}:
        query = query.filter(SessionModel.course_id.in_(staff_course_ids(db, current_user)))

    if course_id:
        if current_user.get("role") in {"instructor", "ta"}:
            require_course_staff_access(db, current_user, str(course_id))
        query = query.filter(SessionModel.course_id == str(course_id))
    if session_id:
        if current_user.get("role") in {"instructor", "ta"}:
            requested_session = db.query(SessionModel).filter(
                SessionModel.id == str(session_id)
            ).first()
            if requested_session:
                require_course_staff_access(db, current_user, requested_session.course_id)
        query = query.filter(AttendanceRecord.session_id == str(session_id))

    total = query.count()
    records = query.order_by(AttendanceRecord.checked_in_at.desc()).limit(limit).all()

    return {
        "items": [
            FlaggedCheckinItem(
                id=rec.id,
                session_id=rec.session_id,
                session_name=rec.session.name if rec.session else "",
                student_id=rec.student_id,
                student_name=rec.student.full_name if rec.student else "",
                status=CheckinStatus(rec.status),
                checked_in_at=rec.checked_in_at,
                risk_score=rec.risk_score,
                risk_factors=json.loads(rec.risk_factors) if rec.risk_factors else [],
                appeal_reason=rec.appeal_reason,
                appealed_at=rec.appealed_at
            )
            for rec in records
        ],
        "total": total,
    }

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

    student_id = str(current_user.get("id"))

    query = (
        db.query(AttendanceRecord)
        .join(AttendanceRecord.session)
        .outerjoin(SessionModel.course)
        .filter(AttendanceRecord.student_id == student_id)
    )

    if course_id:
        query = query.filter(SessionModel.course_id == str(course_id))

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
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == str(checkin_id)).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in with ID '{checkin_id}' not found."
        )

    user_id = str(current_user.get("id"))
    user_role = current_user.get("role")

    is_owner = record.student_id == user_id
    is_staff = user_role in ["instructor", "ta", "admin"]

    if not (is_owner or is_staff):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You do not have permission to view this check-in."
        )
    if user_role in {"instructor", "ta"}:
        session_obj = db.query(SessionModel).filter(
            SessionModel.id == record.session_id
        ).first()
        if session_obj:
            require_course_staff_access(db, current_user, session_obj.course_id)

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

    student_id = str(current_user.get("id"))
    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == str(id)).first()

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

    record = db.query(AttendanceRecord).filter(AttendanceRecord.id == str(id)).first()
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Check-in with ID '{id}' not found."
        )
    if reviewer_role in {"instructor", "ta"}:
        session_obj = db.query(SessionModel).filter(
            SessionModel.id == record.session_id
        ).first()
        if session_obj:
            require_course_staff_access(db, current_user, session_obj.course_id)

    reviewer_id = str(current_user.get("id"))
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
    if current_user.get("role") == "instructor":
        query = query.filter(
            SessionModel.course_id.in_(staff_course_ids(db, current_user))
        )

    if session_id:
        if current_user.get("role") == "instructor":
            requested_session = db.query(SessionModel).filter(
                SessionModel.id == str(session_id)
            ).first()
            if requested_session:
                require_course_staff_access(db, current_user, requested_session.course_id)
        query = query.filter(AttendanceRecord.session_id == str(session_id))
    if course_id:
        if current_user.get("role") == "instructor":
            require_course_staff_access(db, current_user, str(course_id))
        query = query.filter(SessionModel.course_id == str(course_id))
    if student_id:
        query = query.filter(AttendanceRecord.student_id == str(student_id))
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
async def create_checkin(
    payload: CheckinCreate,
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Only students can perform check-ins."
        )

    student_id = str(current_user.get("id"))
    session_id = str(payload.session_id)

    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
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

    now = datetime.now(timezone.utc).replace(tzinfo=None)

    checkin_opens_at = session_obj.checkin_opens_at
    checkin_closes_at = session_obj.checkin_closes_at
    if checkin_opens_at.tzinfo is not None:
        checkin_opens_at = checkin_opens_at.replace(tzinfo=None)
    if checkin_closes_at.tzinfo is not None:
        checkin_closes_at = checkin_closes_at.replace(tzinfo=None)
    if now < checkin_opens_at or now > checkin_closes_at:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Check-in window is closed for this session."
        )

    if not (1.15 <= payload.latitude <= 1.4833 and 103.60 <= payload.longitude <= 104.4167):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Check-ins are only allowed within Singapore."
        )

    existing_checkin = (
        db.query(CheckinModel)
        .filter(
            CheckinModel.session_id == session_id,
            CheckinModel.student_id == student_id
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
        qr_expires_at = session_obj.qr_code_expires_at
        if qr_expires_at and qr_expires_at.tzinfo is not None:
            qr_expires_at = qr_expires_at.replace(tzinfo=None)
        if qr_expires_at and now > qr_expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="QR code for this session has expired."
            )

    risk_factors: List[Dict[str, Any]] = []
    local_risk = 0.0
    distance_meters = None
    geofence_exceeded_critical = False
    outside_singapore_ip = False

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
            local_risk = 1.0
        elif distance_meters > max_radius:
            risk_factors.append({"type": "geo_out_of_bounds", "severity": "high", "weight": 0.40})
            local_risk = max(local_risk, 0.40)

    liveness_passed = None
    liveness_score = None
    face_match_passed = None
    face_match_score = None
    face_embedding_hash = None
    module3_unavailable = False

    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    device = (
        db.query(DeviceModel)
        .filter(
            DeviceModel.device_fingerprint == payload.device_fingerprint,
            DeviceModel.user_id == student_id,
            DeviceModel.is_active.is_(True),
        )
        .first()
    )

    if payload.liveness_challenge_response:
        try:
            liveness_result = await check_liveness(
                payload.liveness_challenge_response,
                challenge_type="passive",
                reference_template_hash=student.face_embedding_hash,
            )
            liveness_passed = bool(liveness_result["liveness_passed"])
            liveness_score = float(liveness_result["liveness_score"])
            face_embedding_hash = liveness_result.get("face_embedding_hash")
        except FaceServiceError as exc:
            if exc.status_code < 500:
                raise HTTPException(exc.status_code, exc.detail) from exc
            module3_unavailable = True
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Face recognition service returned an invalid liveness response",
            ) from exc
    elif session_obj.require_liveness_check:
        liveness_passed = False
        liveness_score = 0.0

    if session_obj.require_liveness_check and liveness_passed is False:
        risk_factors.append({"type": "liveness_failed", "severity": "high", "weight": 1.0})
        local_risk = 1.0

    if session_obj.require_face_match:
        if not payload.liveness_challenge_response:
            face_match_passed = False
            face_match_score = 0.0
        elif not student.face_enrolled or not student.face_embedding_hash:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Face enrollment is required for this session.",
            )
        else:
            try:
                face_result = await verify_face(
                    payload.liveness_challenge_response,
                    student.face_embedding_hash,
                )
                face_match_passed = bool(face_result["match_passed"])
                face_match_score = float(face_result["match_score"])
                face_embedding_hash = face_result.get("current_template_hash")
            except FaceServiceError as exc:
                if exc.status_code < 500:
                    raise HTTPException(exc.status_code, exc.detail) from exc
                module3_unavailable = True
            except (KeyError, TypeError, ValueError) as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Face recognition service returned an invalid verification response",
                ) from exc

        if face_match_passed is False:
            risk_factors.append({"type": "face_match_failed", "severity": "high", "weight": 1.0})
            local_risk = 1.0

    if device is None:
        risk_factors.append({"type": "device_unknown", "severity": "medium", "weight": 0.15})
        local_risk = max(local_risk, 0.15)

    module3_risk = 0.0
    if not module3_unavailable:
        try:
            risk_result = await assess_risk(
                liveness_score=(
                    liveness_score
                    if liveness_score is not None
                    else (0.0 if session_obj.require_liveness_check else 1.0)
                ),
                face_match_score=(
                    face_match_score
                    if face_match_score is not None
                    else (0.0 if session_obj.require_face_match else 1.0)
                ),
                device_public_key=device.public_key if device else None,
                ip_address=client_ip(request),
                user_agent=request.headers.get("user-agent"),
                latitude=payload.latitude,
                longitude=payload.longitude,
                accuracy=payload.location_accuracy_meters,
            )
            module3_risk = float(risk_result["risk_score"])
            signal_breakdown = risk_result.get("signal_breakdown", {})
            outside_singapore_ip = float(signal_breakdown.get("ip_country", 0.0)) >= 1.0
            for signal_name, signal_risk in signal_breakdown.items():
                signal_risk = float(signal_risk)
                if signal_risk <= 0:
                    continue
                severity = (
                    "high"
                    if signal_risk >= 0.7
                    else "medium"
                    if signal_risk >= 0.3
                    else "low"
                )
                risk_factors.append({
                    "type": f"{signal_name}_risk",
                    "severity": severity,
                    "weight": round(signal_risk, 4),
                })
        except FaceServiceError as exc:
            if exc.status_code < 500:
                raise HTTPException(exc.status_code, exc.detail) from exc
            module3_unavailable = True
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Face recognition service returned an invalid risk response",
            ) from exc

    if module3_unavailable:
        risk_factors.append({
            "type": "face_service_unavailable",
            "severity": "high",
            "weight": 0.50,
        })
        local_risk = max(local_risk, 0.50)

    total_risk = round(min(max(local_risk, module3_risk), 1.0), 4)

    verification_failed = (
        bool(payload.liveness_challenge_response)
        and (
            (session_obj.require_liveness_check and liveness_passed is False)
            or (session_obj.require_face_match and face_match_passed is False)
        )
    )

    if geofence_exceeded_critical or outside_singapore_ip or verification_failed:
        checkin_status = CheckinStatus.rejected
    else:
        threshold = session_obj.risk_threshold or 0.50
        if total_risk >= threshold:
            checkin_status = CheckinStatus.flagged
        else:
            checkin_status = CheckinStatus.approved

    new_record = CheckinModel(
        id=str(uuid.uuid4()),
        session_id=session_id,
        student_id=student_id,
        device_id=device.id if device else None,
        status=checkin_status.value,
        checked_in_at=now,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location_accuracy_meters=payload.location_accuracy_meters,
        distance_from_venue_meters=distance_meters,
        liveness_passed=liveness_passed,
        liveness_score=liveness_score,
        liveness_challenge_type=(
            "passive" if payload.liveness_challenge_response else None
        ),
        face_match_passed=face_match_passed,
        face_match_score=face_match_score,
        face_embedding_hash=face_embedding_hash,
        risk_score=total_risk,
        risk_factors=json.dumps(risk_factors),
        qr_code_verified=bool(session_obj.qr_code_secret),
    )

    db.add(new_record)
    add_audit_log(
        db,
        request,
        "checkin_attempted",
        user_id=student_id,
        resource_type="checkin",
        resource_id=new_record.id,
        details=f"session_id={session_id}; status={checkin_status.value}; risk_score={total_risk}",
        success=checkin_status != CheckinStatus.rejected,
    )
    if checkin_status in (CheckinStatus.approved, CheckinStatus.rejected):
        add_audit_log(
            db,
            request,
            "checkin_approved" if checkin_status == CheckinStatus.approved else "checkin_rejected",
            user_id=student_id,
            resource_type="checkin",
            resource_id=new_record.id,
            details=f"session_id={session_id}; risk_score={total_risk}",
            success=checkin_status == CheckinStatus.approved,
        )
    db.commit()
    db.refresh(new_record)

    return {
        "id": new_record.id,
        "session_id": new_record.session_id,
        "student_id": new_record.student_id,
        "status": new_record.status,
        "checked_in_at": new_record.checked_in_at,
        "latitude": new_record.latitude,
        "longitude": new_record.longitude,
        "distance_from_venue_meters": new_record.distance_from_venue_meters,
        "liveness_passed": new_record.liveness_passed,
        "liveness_score": new_record.liveness_score,
        "liveness_challenge_type": new_record.liveness_challenge_type,
        "face_match_passed": new_record.face_match_passed,
        "face_match_score": new_record.face_match_score,
        "risk_score": new_record.risk_score,
        "risk_factors": risk_factors,
    }
