from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..course_access import require_course_staff_access, staff_course_ids
from ..database import get_db
from ..models import (
    CheckinModel,
    CourseModel,
    EnrollmentModel,
    SessionModel,
    UserModel,
)
from ..security import require_roles

router = APIRouter(prefix="/stats", tags=["Statistics"])

INSTRUCTOR_OR_ADMIN = require_roles("instructor", "admin")
STAFF = require_roles("ta", "instructor", "admin")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _scoped_course_ids(db: Session, user: Dict[str, Any]) -> Optional[list[str]]:
    if user.get("role") == "admin":
        return None
    return staff_course_ids(db, user)


def _get_session(db: Session, session_id: str) -> SessionModel:
    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found.",
        )
    return session


def _get_course(db: Session, course_id: str) -> CourseModel:
    course = db.query(CourseModel).filter(CourseModel.id == course_id).first()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found.",
        )
    return course


def _active_enrollment_count(db: Session, course_id: str) -> int:
    return (
        db.query(func.count(EnrollmentModel.id))
        .filter(
            EnrollmentModel.course_id == course_id,
            EnrollmentModel.is_active.is_(True),
        )
        .scalar()
        or 0
    )


@router.get("/overview")
def stats_overview(
    course_id: Optional[str] = None,
    days: int = Query(7, ge=1, le=365),
    user: Dict[str, Any] = Depends(INSTRUCTOR_OR_ADMIN),
    db: Session = Depends(get_db),
):
    scoped_course_ids = _scoped_course_ids(db, user)
    if course_id:
        _get_course(db, course_id)
        if user.get("role") != "admin":
            require_course_staff_access(db, user, course_id)
        scoped_course_ids = [course_id]

    sessions_query = db.query(SessionModel)
    courses_query = db.query(CourseModel)
    checkins_query = db.query(CheckinModel).join(
        SessionModel, CheckinModel.session_id == SessionModel.id
    )
    if scoped_course_ids is not None:
        sessions_query = sessions_query.filter(SessionModel.course_id.in_(scoped_course_ids))
        courses_query = courses_query.filter(CourseModel.id.in_(scoped_course_ids))
        checkins_query = checkins_query.filter(SessionModel.course_id.in_(scoped_course_ids))

    now = _utc_now()
    # Calendar-day reports use Singapore time; persisted timestamps are UTC.
    today_start = (now + timedelta(hours=8)).replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(hours=8)
    week_start = today_start - timedelta(days=6)
    trend_start = today_start - timedelta(days=days - 1)

    total_sessions = sessions_query.count()
    active_sessions = sessions_query.filter(SessionModel.status == "active").count()
    total_courses = courses_query.count()
    if scoped_course_ids is None:
        total_students = db.query(UserModel).filter(UserModel.role == "student").count()
    else:
        total_students = (
            db.query(func.count(func.distinct(EnrollmentModel.student_id)))
            .filter(
                EnrollmentModel.course_id.in_(scoped_course_ids),
                EnrollmentModel.is_active.is_(True),
            )
            .scalar()
            or 0
        )

    checkins_today_query = checkins_query.filter(CheckinModel.checked_in_at >= today_start)
    checkins_week_query = checkins_query.filter(CheckinModel.checked_in_at >= week_start)
    total_checkins_today = checkins_today_query.count()
    total_checkins_week = checkins_week_query.count()
    total_checkins = checkins_query.count()
    approved_checkins = checkins_query.filter(CheckinModel.status == "approved").count()
    flagged_pending = checkins_query.filter(
        CheckinModel.status.in_(["flagged", "appealed"])
    ).count()
    average_risk_score = (
        checkins_query.with_entities(func.avg(CheckinModel.risk_score)).scalar() or 0.0
    )
    high_risk_today = checkins_today_query.filter(CheckinModel.risk_score >= 0.5).count()

    enrollment_counts = dict(
        db.query(EnrollmentModel.course_id, func.count(EnrollmentModel.id))
        .filter(
            EnrollmentModel.is_active.is_(True),
            *(
                [EnrollmentModel.course_id.in_(scoped_course_ids)]
                if scoped_course_ids is not None
                else []
            ),
        )
        .group_by(EnrollmentModel.course_id)
        .all()
    )
    session_counts = dict(
        db.query(SessionModel.course_id, func.count(SessionModel.id))
        .filter(
            *(
                [SessionModel.course_id.in_(scoped_course_ids)]
                if scoped_course_ids is not None
                else []
            )
        )
        .group_by(SessionModel.course_id)
        .all()
    )
    attendance_opportunities = sum(
        enrollment_counts.get(cid, 0) * count
        for cid, count in session_counts.items()
    )
    attendance_rate = (
        round(approved_checkins / attendance_opportunities, 2)
        if attendance_opportunities
        else 0.0
    )

    report_day = (func.date(CheckinModel.checked_in_at, "+8 hours")
                  if db.get_bind().dialect.name == "sqlite"
                  else func.date(CheckinModel.checked_in_at + timedelta(hours=8)))
    daily_rows = (
        checkins_query.filter(CheckinModel.checked_in_at >= trend_start)
        .with_entities(
            report_day,
            CheckinModel.status,
            func.count(CheckinModel.id),
        )
        .group_by(report_day, CheckinModel.status)
        .all()
    )
    daily_totals: dict[str, int] = {}
    daily_approved: dict[str, int] = {}
    for day, checkin_status, count in daily_rows:
        day_key = day.isoformat() if hasattr(day, "isoformat") else str(day)
        daily_totals[day_key] = daily_totals.get(day_key, 0) + count
        if checkin_status == "approved":
            daily_approved[day_key] = daily_approved.get(day_key, 0) + count

    trends = [
        {
            "date": (today_start + timedelta(hours=8) - timedelta(days=delta)).date().isoformat(),
            "count": daily_totals.get(
                (today_start + timedelta(hours=8) - timedelta(days=delta)).date().isoformat(), 0
            ),
            "rate": (
                round(
                    daily_approved.get(
                        (today_start + timedelta(hours=8) - timedelta(days=delta)).date().isoformat(), 0
                    )
                    / daily_totals[
                        (today_start + timedelta(hours=8) - timedelta(days=delta)).date().isoformat()
                    ],
                    2,
                )
                if daily_totals.get(
                    (today_start + timedelta(hours=8) - timedelta(days=delta)).date().isoformat(), 0
                )
                else 0.0
            ),
        }
        for delta in range(days - 1, -1, -1)
    ]

    approval_rate = round(approved_checkins / total_checkins, 2) if total_checkins else 0.0
    return {
        "total_sessions": total_sessions,
        "active_sessions": active_sessions,
        "total_courses": total_courses,
        "total_students": total_students,
        "today_checkins": total_checkins_today,
        "flagged_pending": flagged_pending,
        "approval_rate": approval_rate,
        "total_checkins_today": total_checkins_today,
        "total_checkins_week": total_checkins_week,
        "average_attendance_rate": attendance_rate,
        "flagged_pending_review": flagged_pending,
        "average_risk_score": round(float(average_risk_score), 2),
        "high_risk_checkins_today": high_risk_today,
        "trends": {
            "checkins_by_day": [
                {"date": row["date"], "count": row["count"]} for row in trends
            ],
            "attendance_rate_by_day": [
                {"date": row["date"], "rate": row["rate"]} for row in trends
            ],
        },
    }


@router.get("/sessions/{session_id}")
def stats_session(
    session_id: str,
    user: Dict[str, Any] = Depends(STAFF),
    db: Session = Depends(get_db),
):
    session = _get_session(db, session_id)
    if user.get("role") != "admin":
        require_course_staff_access(db, user, session.course_id)

    checkins = db.query(CheckinModel).filter(CheckinModel.session_id == session_id).all()
    status_counts = {
        value: sum(1 for checkin in checkins if checkin.status == value)
        for value in ("approved", "flagged", "rejected", "pending", "appealed")
    }
    enrolled = _active_enrollment_count(db, session.course_id)
    approved = status_counts["approved"]
    valid_distances = [
        checkin.distance_from_venue_meters
        for checkin in checkins
        if checkin.distance_from_venue_meters is not None
    ]
    average_risk = (
        sum(checkin.risk_score or 0.0 for checkin in checkins) / len(checkins)
        if checkins
        else 0.0
    )
    timeline_counts: dict[int, int] = {}
    checkin_minutes = []
    scheduled_start = session.scheduled_start
    if scheduled_start.tzinfo is None:
        scheduled_start = scheduled_start.replace(tzinfo=timezone.utc)
    for checkin in checkins:
        checked_in_at = checkin.checked_in_at
        if checked_in_at is None:
            continue
        if checked_in_at.tzinfo is None:
            checked_in_at = checked_in_at.replace(tzinfo=timezone.utc)
        minutes = max(
            0.0, (checked_in_at - scheduled_start).total_seconds() / 60.0
        )
        checkin_minutes.append(minutes)
        bucket = int(minutes // 5) * 5
        timeline_counts[bucket] = timeline_counts.get(bucket, 0) + 1
    course = db.query(CourseModel).filter(CourseModel.id == session.course_id).first()
    return {
        "session_id": session.id,
        "session_name": session.name,
        "course_code": course.code if course else "",
        "scheduled_start": session.scheduled_start,
        "status": session.status,
        "total_enrolled": enrolled,
        "checked_in": len(checkins),
        "checked_in_count": len(checkins),
        "approved_count": approved,
        "flagged_count": status_counts["flagged"] + status_counts["appealed"],
        "attendance_rate": round(approved / enrolled, 2) if enrolled else 0.0,
        "by_status": status_counts,
        "average_risk_score": round(average_risk, 2),
        "average_distance_meters": round(
            sum(valid_distances) / len(valid_distances), 1
        )
        if valid_distances
        else 0.0,
        "average_checkin_time_minutes": round(
            sum(checkin_minutes) / len(checkin_minutes), 1
        )
        if checkin_minutes
        else 0.0,
        "risk_distribution": {
            "low": sum(1 for item in checkins if item.risk_score < 0.3),
            "medium": sum(1 for item in checkins if 0.3 <= item.risk_score < 0.5),
            "high": sum(1 for item in checkins if item.risk_score >= 0.5),
        },
        "checkin_timeline": [
            {"minute": minute, "count": timeline_counts[minute]}
            for minute in sorted(timeline_counts)
        ],
    }


@router.get("/courses/{course_id}")
def stats_course(
    course_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    user: Dict[str, Any] = Depends(INSTRUCTOR_OR_ADMIN),
    db: Session = Depends(get_db),
):
    course = _get_course(db, course_id)
    if user.get("role") != "admin":
        require_course_staff_access(db, user, course_id)

    sessions_query = db.query(SessionModel).filter(SessionModel.course_id == course_id)
    if start_date:
        sessions_query = sessions_query.filter(SessionModel.scheduled_start >= start_date)
    if end_date:
        sessions_query = sessions_query.filter(SessionModel.scheduled_start <= end_date)
    sessions = sessions_query.order_by(SessionModel.scheduled_start.asc()).all()
    enrollments = (
        db.query(EnrollmentModel, UserModel)
        .join(UserModel, EnrollmentModel.student_id == UserModel.id)
        .filter(
            EnrollmentModel.course_id == course_id,
            EnrollmentModel.is_active.is_(True),
        )
        .all()
    )
    session_ids = [session.id for session in sessions]
    checkins = (
        db.query(CheckinModel)
        .filter(CheckinModel.session_id.in_(session_ids))
        .all()
        if session_ids
        else []
    )
    by_session: dict[str, list[CheckinModel]] = {}
    by_student: dict[str, list[CheckinModel]] = {}
    for checkin in checkins:
        by_session.setdefault(checkin.session_id, []).append(checkin)
        by_student.setdefault(checkin.student_id, []).append(checkin)

    enrolled_count = len(enrollments)
    session_rows = []
    approved_total = 0
    for session in sessions:
        session_checkins = by_session.get(session.id, [])
        approved = sum(1 for item in session_checkins if item.status == "approved")
        approved_total += approved
        session_rows.append(
            {
                "session_id": session.id,
                "name": session.name,
                "date": session.scheduled_start.date().isoformat(),
                "attendance_rate": round(approved / enrolled_count, 2)
                if enrolled_count
                else 0.0,
                "checked_in": approved,
            }
        )

    student_rows = []
    low_attendance = []
    for _, student in enrollments:
        student_checkins = by_student.get(student.id, [])
        attended = len(
            {
                item.session_id
                for item in student_checkins
                if item.status == "approved"
            }
        )
        rate = round(attended / len(sessions), 2) if sessions else 0.0
        risk_average = (
            sum(item.risk_score or 0.0 for item in student_checkins)
            / len(student_checkins)
            if student_checkins
            else 0.0
        )
        student_rows.append(
            {
                "student_id": student.id,
                "student_name": student.full_name,
                "sessions_attended": attended,
                "attendance_rate": rate,
                "average_risk_score": round(risk_average, 2),
            }
        )
        if sessions and rate <= 0.7:
            low_attendance.append(
                {
                    "student_id": student.id,
                    "student_name": student.full_name,
                    "attendance_rate": rate,
                    "sessions_missed": len(sessions) - attended,
                }
            )

    attendance_opportunities = len(sessions) * enrolled_count
    return {
        "course_id": course.id,
        "course_code": course.code,
        "course_name": course.name,
        "total_enrolled": enrolled_count,
        "total_sessions": len(sessions),
        "average_attendance_rate": round(approved_total / attendance_opportunities, 2)
        if attendance_opportunities
        else 0.0,
        "overall_attendance_rate": round(approved_total / attendance_opportunities, 2)
        if attendance_opportunities
        else 0.0,
        "flagged_checkins": sum(
            1 for checkin in checkins if checkin.status in {"flagged", "appealed"}
        ),
        "sessions": session_rows,
        "student_attendance": student_rows,
        "low_attendance_alerts": low_attendance,
    }


@router.get("/students/{student_id}")
def stats_student(
    student_id: str,
    user: Dict[str, Any] = Depends(INSTRUCTOR_OR_ADMIN),
    db: Session = Depends(get_db),
):
    student = (
        db.query(UserModel)
        .filter(UserModel.id == student_id, UserModel.role == "student")
        .first()
    )
    if student is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Student with ID '{student_id}' not found.",
        )

    enrollments = (
        db.query(EnrollmentModel)
        .filter(
            EnrollmentModel.student_id == student_id,
            EnrollmentModel.is_active.is_(True),
        )
        .all()
    )
    course_ids = [enrollment.course_id for enrollment in enrollments]
    if user.get("role") != "admin":
        allowed = set(staff_course_ids(db, user))
        course_ids = [course_id for course_id in course_ids if course_id in allowed]
        if not course_ids:
            raise HTTPException(403, "Access denied. Student is not enrolled in your courses.")

    sessions = (
        db.query(SessionModel)
        .filter(SessionModel.course_id.in_(course_ids))
        .all()
        if course_ids
        else []
    )
    checkins = (
        db.query(CheckinModel, SessionModel, CourseModel)
        .join(SessionModel, CheckinModel.session_id == SessionModel.id)
        .join(CourseModel, SessionModel.course_id == CourseModel.id)
        .filter(
            CheckinModel.student_id == student_id,
            SessionModel.course_id.in_(course_ids),
        )
        .order_by(CheckinModel.checked_in_at.desc())
        .all()
        if course_ids
        else []
    )
    attended = {row[1].id for row in checkins if row[0].status == "approved"}
    course_by_id = (
        {
            course.id: course
            for course in db.query(CourseModel)
            .filter(CourseModel.id.in_(course_ids))
            .all()
        }
        if course_ids
        else {}
    )
    checkin_rows = [
        {
            "session_name": session.name,
            "course_code": course.code,
            "checked_in_at": checkin.checked_in_at,
            "status": checkin.status,
        }
        for checkin, session, course in checkins[:10]
        if session.course_id in course_by_id
    ]
    course_rows = []
    for course_id in course_ids:
        course = course_by_id.get(course_id)
        if course is None:
            continue
        course_sessions = [
            session for session in sessions if session.course_id == course_id
        ]
        course_checkins = [
            checkin
            for checkin, session, _ in checkins
            if session.course_id == course_id
        ]
        attended_count = len(
            {
                checkin.session_id
                for checkin in course_checkins
                if checkin.status == "approved"
            }
        )
        course_rows.append(
            {
                "course_id": course.id,
                "course_code": course.code,
                "attendance_rate": round(attended_count / len(course_sessions), 2)
                if course_sessions
                else 0.0,
                "sessions_attended": attended_count,
                "total_sessions": len(course_sessions),
                "average_risk_score": round(
                    sum(item.risk_score or 0.0 for item in course_checkins)
                    / len(course_checkins),
                    2,
                )
                if course_checkins
                else 0.0,
            }
        )
    return {
        "student_id": student.id,
        "student_name": student.full_name,
        "student_email": student.email,
        "total_enrolled_courses": len(course_ids),
        "total_sessions": len(sessions),
        "attended_sessions": len(attended),
        "attendance_rate": round(len(attended) / len(sessions), 2) if sessions else 0.0,
        "courses": course_rows,
        "recent_checkins": checkin_rows,
        "recent_sessions": checkin_rows,
    }
