import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, ForeignKey, create_engine, func, cast, Date, and_
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import declarative_base, sessionmaker, Session, relationship
import enum

from database import get_db
from security import get_current_user

Base = declarative_base()

# --- PostgreSQL ENUM Definitions ---
class UserRole(str, enum.Enum):
    student = "student"
    instructor = "instructor"
    ta = "ta"
    admin = "admin"

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

class RiskSignalSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"

# --- SQLAlchemy Models for PostgreSQL Schema ---
class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(UUID(as_uuid=True), primary_key=True)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    status = Column(
        PG_ENUM(SessionStatus, name="session_status", create_type=False),
        nullable=False,
        default=SessionStatus.scheduled
    )

class Checkin(Base):
    __tablename__ = "checkins"

    id = Column(String(36), primary_key=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    student_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    status = Column(
        PG_ENUM(CheckinStatus, name="checkin_status", create_type=False),
        nullable=False
    )
    checked_in_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    risk_score = Column(Float, nullable=False, default=0.0)

    session = relationship("SessionModel", backref="checkins")
    risk_signals = relationship("RiskSignal", backref="checkin", cascade="all, delete-orphan")

class RiskSignal(Base):
    __tablename__ = "risk_signals"

    id = Column(String(36), primary_key=True)
    checkin_id = Column(String(36), ForeignKey("checkins.id"), nullable=False)
    severity = Column(
        PG_ENUM(RiskSignalSeverity, name="risk_signal_severity", create_type=False),
        nullable=False
    )
    detected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

# --- Response Schemas ---
class DailyCheckinTrend(BaseModel):
    date: str
    count: int

class DailyAttendanceRateTrend(BaseModel):
    date: str
    rate: float

class TrendsData(BaseModel):
    checkins_by_day: List[DailyCheckinTrend]
    attendance_rate_by_day: List[DailyAttendanceRateTrend]

class StatsOverviewResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_sessions: int
    active_sessions: int
    total_checkins_today: int
    total_checkins_week: int
    average_attendance_rate: float
    flagged_pending_review: int
    approval_rate: float
    average_risk_score: float
    high_risk_checkins_today: int
    trends: TrendsData

# --- Router ---
router = APIRouter(prefix="/stats", tags=["Statistics"])

@router.get("/overview", response_model=StatsOverviewResponse, status_code=status.HTTP_200_OK)
def get_stats_overview(
    course_id: Optional[uuid.UUID] = Query(None, description="Filter stats by course"),
    days: int = Query(7, ge=1, le=365, description="Number of days for trends"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or admin permissions required."
        )

    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    week_start = now - timedelta(days=7)
    trend_start_datetime = datetime.combine((now - timedelta(days=days - 1)).date(), datetime.min.time(), tzinfo=timezone.utc)

    # 1. Sessions Count
    session_query = db.query(SessionModel)
    if course_id:
        session_query = session_query.filter(SessionModel.course_id == course_id)

    total_sessions = session_query.count()
    active_sessions = session_query.filter(SessionModel.status == SessionStatus.active).count()

    # 2. Check-ins Count
    checkin_query = db.query(Checkin).join(Checkin.session)
    if course_id:
        checkin_query = checkin_query.filter(SessionModel.course_id == course_id)

    total_checkins_today = checkin_query.filter(Checkin.checked_in_at >= today_start).count()
    total_checkins_week = checkin_query.filter(Checkin.checked_in_at >= week_start).count()

    flagged_pending_review = checkin_query.filter(
        Checkin.status.in_([CheckinStatus.flagged, CheckinStatus.appealed])
    ).count()

    # High Risk Check-ins Today
    high_risk_query = (
        db.query(func.count(func.distinct(Checkin.id)))
        .join(Checkin.session)
        .join(Checkin.risk_signals)
        .filter(
            Checkin.checked_in_at >= today_start,
            RiskSignal.severity.in_([RiskSignalSeverity.high, RiskSignalSeverity.critical])
        )
    )
    if course_id:
        high_risk_query = high_risk_query.filter(SessionModel.course_id == course_id)
    high_risk_count = high_risk_query.scalar() or 0

    # Calculated Aggregates
    total_checkins_count = checkin_query.count()
    if total_checkins_count > 0:
        approved_count = checkin_query.filter(Checkin.status == CheckinStatus.approved).count()
        approval_rate = round(approved_count / total_checkins_count, 2)

        avg_risk = checkin_query.with_entities(func.avg(Checkin.risk_score)).scalar()
        average_risk_score = round(float(avg_risk), 2) if avg_risk is not None else 0.0
        average_attendance_rate = round(approved_count / total_checkins_count, 2)
    else:
        approval_rate = 0.0
        average_risk_score = 0.0
        average_attendance_rate = 0.0

    # 3. Trends Aggregations
    daily_records = (
        checkin_query
        .filter(Checkin.checked_in_at >= trend_start_datetime)
        .with_entities(
            cast(Checkin.checked_in_at, Date).label("checkin_date"),
            Checkin.status,
            func.count(Checkin.id).label("count")
        )
        .group_by("checkin_date", Checkin.status)
        .all()
    )

    daily_totals: Dict[str, int] = {}
    daily_approved: Dict[str, int] = {}

    for row in daily_records:
        if not row.checkin_date:
            continue
        d_str = row.checkin_date.strftime("%Y-%m-%d")
        daily_totals[d_str] = daily_totals.get(d_str, 0) + row.count
        if row.status == CheckinStatus.approved:
            daily_approved[d_str] = daily_approved.get(d_str, 0) + row.count

    checkins_by_day = []
    attendance_rate_by_day = []

    for i in range(days - 1, -1, -1):
        day_date = (now - timedelta(days=i)).date()
        date_str = day_date.strftime("%Y-%m-%d")
        
        total_d = daily_totals.get(date_str, 0)
        approved_d = daily_approved.get(date_str, 0)
        
        checkins_by_day.append(DailyCheckinTrend(date=date_str, count=total_d))
        
        rate = round(approved_d / total_d, 2) if total_d > 0 else 0.0
        attendance_rate_by_day.append(DailyAttendanceRateTrend(date=date_str, rate=rate))

    return StatsOverviewResponse(
        total_sessions=total_sessions,
        active_sessions=active_sessions,
        total_checkins_today=total_checkins_today,
        total_checkins_week=total_checkins_week,
        average_attendance_rate=average_attendance_rate,
        flagged_pending_review=flagged_pending_review,
        approval_rate=approval_rate,
        average_risk_score=average_risk_score,
        high_risk_checkins_today=high_risk_count,
        trends=TrendsData(
            checkins_by_day=checkins_by_day,
            attendance_rate_by_day=attendance_rate_by_day
        )
    )