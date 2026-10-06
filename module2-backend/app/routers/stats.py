import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, String, Float, DateTime, ForeignKey, func, cast, Date
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM
from sqlalchemy.orm import declarative_base, Session, relationship
import enum

from database import get_db
from security import get_current_user

Base = declarative_base()

# =====================================================================
# Database Models & Enums
# =====================================================================

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

class User(Base):
    __tablename__ = "users"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)

class Course(Base):
    __tablename__ = "courses"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code = Column(String(20), nullable=False)
    name = Column(String(255), nullable=False)

class Enrollment(Base):
    __tablename__ = "enrollments"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)

    course = relationship("Course", backref="enrollments")
    student = relationship("User", backref="enrollments")

class SessionModel(Base):
    __tablename__ = "sessions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    name = Column(String(255), nullable=False)
    scheduled_start = Column(DateTime(timezone=True), nullable=False)
    status = Column(
        PG_ENUM(SessionStatus, name="session_status", create_type=False),
        nullable=False,
        default=SessionStatus.scheduled
    )

    course = relationship("Course", backref="sessions")

class Checkin(Base):
    __tablename__ = "checkins"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("sessions.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(
        PG_ENUM(CheckinStatus, name="checkin_status", create_type=False),
        nullable=False
    )
    checked_in_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    distance_from_venue_meters = Column(Float, nullable=True)
    risk_score = Column(Float, nullable=False, default=0.0)

    session = relationship("SessionModel", backref="checkins")
    student = relationship("User", backref="checkins")
    risk_signals = relationship("RiskSignal", backref="checkin", cascade="all, delete-orphan")

class RiskSignal(Base):
    __tablename__ = "risk_signals"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    checkin_id = Column(UUID(as_uuid=True), ForeignKey("checkins.id"), nullable=False)
    severity = Column(
        PG_ENUM(RiskSignalSeverity, name="risk_signal_severity", create_type=False),
        nullable=False
    )
    detected_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


# =====================================================================
# Pydantic Schemas
# =====================================================================

# --- Overview Schemas ---
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

# --- Session Stats Schemas ---
class ByStatus(BaseModel):
    approved: int = 0
    flagged: int = 0
    rejected: int = 0
    pending: int = 0

class RiskDistribution(BaseModel):
    low: int = 0
    medium: int = 0
    high: int = 0

class CheckinTimelineBucket(BaseModel):
    minute: int
    count: int

class SessionStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    session_id: uuid.UUID
    session_name: str
    course_code: str
    scheduled_start: datetime
    status: SessionStatus
    total_enrolled: int
    checked_in: int
    attendance_rate: float
    by_status: ByStatus
    average_risk_score: float
    average_distance_meters: float
    average_checkin_time_minutes: float
    risk_distribution: RiskDistribution
    checkin_timeline: List[CheckinTimelineBucket]

# --- Course Stats Schemas ---
class SessionAttendanceSummary(BaseModel):
    session_id: uuid.UUID
    name: str
    date: str
    attendance_rate: float
    checked_in: int

class StudentAttendanceSummary(BaseModel):
    student_id: uuid.UUID
    student_name: str
    sessions_attended: int
    attendance_rate: float
    average_risk_score: float

class LowAttendanceAlert(BaseModel):
    student_id: uuid.UUID
    student_name: str
    attendance_rate: float
    sessions_missed: int

class CourseStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: uuid.UUID
    course_code: str
    course_name: str
    total_sessions: int
    total_enrolled: int
    overall_attendance_rate: float
    sessions: List[SessionAttendanceSummary]
    student_attendance: List[StudentAttendanceSummary]
    low_attendance_alerts: List[LowAttendanceAlert]

# --- Student Stats Schemas ---
class StudentCourseStats(BaseModel):
    course_id: uuid.UUID
    course_code: str
    attendance_rate: float
    sessions_attended: int
    total_sessions: int
    average_risk_score: float

class StudentRecentCheckin(BaseModel):
    session_name: str
    course_code: str
    checked_in_at: datetime
    status: CheckinStatus

class StudentStatsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    student_id: uuid.UUID
    student_name: str
    student_email: str
    courses: List[StudentCourseStats]
    recent_checkins: List[StudentRecentCheckin]


# =====================================================================
# API Endpoints Router
# =====================================================================

router = APIRouter(prefix="/stats", tags=["Statistics"])

# 1. GET /stats/overview
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

    session_query = db.query(SessionModel)
    if course_id:
        session_query = session_query.filter(SessionModel.course_id == course_id)

    total_sessions = session_query.count()
    active_sessions = session_query.filter(SessionModel.status == SessionStatus.active).count()

    checkin_query = db.query(Checkin).join(Checkin.session)
    if course_id:
        checkin_query = checkin_query.filter(SessionModel.course_id == course_id)

    total_checkins_today = checkin_query.filter(Checkin.checked_in_at >= today_start).count()
    total_checkins_week = checkin_query.filter(Checkin.checked_in_at >= week_start).count()

    flagged_pending_review = checkin_query.filter(
        Checkin.status.in_([CheckinStatus.flagged, CheckinStatus.appealed])
    ).count()

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

# 2. GET /stats/sessions/{session_id}
@router.get("/sessions/{session_id}", response_model=SessionStatsResponse, status_code=status.HTTP_200_OK)
def get_session_stats(
    session_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "ta", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or TA permissions required."
        )

    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found."
        )

    checkins = db.query(Checkin).filter(Checkin.session_id == session_id).all()
    checked_in_count = len(checkins)

    by_status = ByStatus(
        approved=sum(1 for c in checkins if c.status == CheckinStatus.approved),
        flagged=sum(1 for c in checkins if c.status == CheckinStatus.flagged),
        rejected=sum(1 for c in checkins if c.status == CheckinStatus.rejected),
        pending=sum(1 for c in checkins if c.status == CheckinStatus.pending)
    )

    risk_dist = RiskDistribution(
        low=sum(1 for c in checkins if c.risk_score < 0.3),
        medium=sum(1 for c in checkins if 0.3 <= c.risk_score < 0.5),
        high=sum(1 for c in checkins if c.risk_score >= 0.5)
    )

    avg_risk = sum(c.risk_score for c in checkins) / checked_in_count if checked_in_count > 0 else 0.0
    valid_distances = [c.distance_from_venue_meters for c in checkins if c.distance_from_venue_meters is not None]
    avg_distance = sum(valid_distances) / len(valid_distances) if valid_distances else 0.0

    total_enrolled = db.query(Enrollment).filter(Enrollment.course_id == session_obj.course_id).count() or 50
    attendance_rate = round(by_status.approved / total_enrolled, 2) if total_enrolled > 0 else 0.0

    timeline_buckets: Dict[int, int] = {}
    time_deltas = []
    scheduled_start = session_obj.scheduled_start
    if scheduled_start.tzinfo is None:
        scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)

    for c in checkins:
        c_time = c.checked_in_at
        if c_time.tzinfo is None:
            c_time = c_time.replace(tzinfo=timezone.utc)
        delta_minutes = max(0.0, (c_time - scheduled_start).total_seconds() / 60.0)
        time_deltas.append(delta_minutes)
        bucket_minute = int(delta_minutes // 5) * 5
        timeline_buckets[bucket_minute] = timeline_buckets.get(bucket_minute, 0) + 1

    avg_checkin_time = sum(time_deltas) / len(time_deltas) if time_deltas else 0.0

    checkin_timeline = [
        CheckinTimelineBucket(minute=m, count=timeline_buckets[m])
        for m in sorted(timeline_buckets.keys())
    ]

    return SessionStatsResponse(
        session_id=session_obj.id,
        session_name=session_obj.name,
        course_code=session_obj.course.code if session_obj.course else "",
        scheduled_start=session_obj.scheduled_start,
        status=session_obj.status,
        total_enrolled=total_enrolled,
        checked_in=checked_in_count,
        attendance_rate=attendance_rate,
        by_status=by_status,
        average_risk_score=round(avg_risk, 2),
        average_distance_meters=round(avg_distance, 1),
        average_checkin_time_minutes=round(avg_checkin_time, 1),
        risk_distribution=risk_dist,
        checkin_timeline=checkin_timeline
    )

# 3. GET /stats/courses/{course_id}
@router.get("/courses/{course_id}", response_model=CourseStatsResponse, status_code=status.HTTP_200_OK)
def get_course_stats(
    course_id: uuid.UUID,
    start_date: Optional[datetime] = Query(None, description="Start date (ISO8601)"),
    end_date: Optional[datetime] = Query(None, description="End date (ISO8601)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or admin permissions required."
        )

    course_obj = db.query(Course).filter(Course.id == course_id).first()
    if not course_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )

    session_query = db.query(SessionModel).filter(SessionModel.course_id == course_id)
    if start_date:
        session_query = session_query.filter(SessionModel.scheduled_start >= start_date)
    if end_date:
        session_query = session_query.filter(SessionModel.scheduled_start <= end_date)

    course_sessions = session_query.order_by(SessionModel.scheduled_start.asc()).all()
    total_sessions_count = len(course_sessions)
    session_ids = [s.id for s in course_sessions]

    total_enrolled = db.query(Enrollment).filter(Enrollment.course_id == course_id).count() or 50

    session_summaries: List[SessionAttendanceSummary] = []
    total_approved_checkins = 0

    if session_ids:
        all_checkins = db.query(Checkin).filter(Checkin.session_id.in_(session_ids)).all()
        checkins_by_session: Dict[uuid.UUID, List[Checkin]] = {}
        for c in all_checkins:
            checkins_by_session.setdefault(c.session_id, []).append(c)

        for sess in course_sessions:
            s_checkins = checkins_by_session.get(sess.id, [])
            approved_cnt = sum(1 for c in s_checkins if c.status == CheckinStatus.approved)
            total_approved_checkins += approved_cnt
            sess_rate = round(approved_cnt / total_enrolled, 2) if total_enrolled > 0 else 0.0

            session_summaries.append(
                SessionAttendanceSummary(
                    session_id=sess.id,
                    name=sess.name,
                    date=sess.scheduled_start.strftime("%Y-%m-%d"),
                    attendance_rate=sess_rate,
                    checked_in=approved_cnt
                )
            )
    else:
        all_checkins = []

    total_possible_attendances = total_sessions_count * total_enrolled
    overall_attendance_rate = (
        round(total_approved_checkins / total_possible_attendances, 2)
        if total_possible_attendances > 0 else 0.0
    )

    enrollments = db.query(Enrollment).filter(Enrollment.course_id == course_id).all()
    student_attendance_list: List[StudentAttendanceSummary] = []
    low_attendance_alerts: List[LowAttendanceAlert] = []

    checkins_by_student: Dict[uuid.UUID, List[Checkin]] = {}
    for c in all_checkins:
        checkins_by_student.setdefault(c.student_id, []).append(c)

    for enr in enrollments:
        if not enr.student:
            continue
        st = enr.student
        st_checkins = checkins_by_student.get(st.id, [])
        attended_cnt = sum(1 for c in st_checkins if c.status == CheckinStatus.approved)
        st_rate = round(attended_cnt / total_sessions_count, 2) if total_sessions_count > 0 else 0.0
        avg_risk = sum(c.risk_score for c in st_checkins) / len(st_checkins) if st_checkins else 0.0

        student_attendance_list.append(
            StudentAttendanceSummary(
                student_id=st.id,
                student_name=st.full_name,
                sessions_attended=attended_cnt,
                attendance_rate=st_rate,
                average_risk_score=round(avg_risk, 2)
            )
        )

        if st_rate <= 0.70 and total_sessions_count > 0:
            low_attendance_alerts.append(
                LowAttendanceAlert(
                    student_id=st.id,
                    student_name=st.full_name,
                    attendance_rate=st_rate,
                    sessions_missed=total_sessions_count - attended_cnt
                )
            )

    return CourseStatsResponse(
        course_id=course_obj.id,
        course_code=course_obj.code,
        course_name=course_obj.name,
        total_sessions=total_sessions_count,
        total_enrolled=total_enrolled,
        overall_attendance_rate=overall_attendance_rate,
        sessions=session_summaries,
        student_attendance=student_attendance_list,
        low_attendance_alerts=low_attendance_alerts
    )

# 4. GET /stats/students/{student_id}
@router.get("/students/{student_id}", response_model=StudentStatsResponse, status_code=status.HTTP_200_OK)
def get_student_stats(
    student_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or admin permissions required."
        )

    student = db.query(User).filter(User.id == student_id).first()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID '{student_id}' not found."
        )

    enrollments = db.query(Enrollment).filter(Enrollment.student_id == student_id).all()
    enrolled_courses = [e.course for e in enrollments if e.course]

    all_checkins = (
        db.query(Checkin)
        .join(Checkin.session)
        .filter(Checkin.student_id == student_id)
        .order_by(Checkin.checked_in_at.desc())
        .all()
    )

    checkins_by_course: Dict[uuid.UUID, List[Checkin]] = {}
    for c in all_checkins:
        checkins_by_course.setdefault(c.session.course_id, []).append(c)

    courses_stats: List[StudentCourseStats] = []

    for course in enrolled_courses:
        c_checkins = checkins_by_course.get(course.id, [])
        total_sessions = db.query(SessionModel).filter(SessionModel.course_id == course.id).count()
        sessions_attended = sum(1 for c in c_checkins if c.status == CheckinStatus.approved)
        attendance_rate = round(sessions_attended / total_sessions, 2) if total_sessions > 0 else 0.0
        avg_risk = sum(c.risk_score for c in c_checkins) / len(c_checkins) if c_checkins else 0.0

        courses_stats.append(
            StudentCourseStats(
                course_id=course.id,
                course_code=course.code,
                attendance_rate=attendance_rate,
                sessions_attended=sessions_attended,
                total_sessions=total_sessions,
                average_risk_score=round(avg_risk, 2)
            )
        )

    recent_checkins = [
        StudentRecentCheckin(
            session_name=c.session.name if c.session else "",
            course_code=c.session.course.code if c.session and c.session.course else "",
            checked_in_at=c.checked_in_at,
            status=c.status
        )
        for c in all_checkins[:10]
    ]

    return StudentStatsResponse(
        student_id=student.id,
        student_name=student.full_name,
        student_email=student.email,
        courses=courses_stats,
        recent_checkins=recent_checkins
    )