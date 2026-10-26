from __future__ import annotations

import csv
import io
from datetime import date, datetime, time
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from ..audit import add_audit_log
from ..course_access import require_course_staff_access
from ..database import get_db
from ..models import CheckinModel, CourseModel, EnrollmentModel, SessionModel, UserModel
from ..security import get_current_user

router = APIRouter(prefix="/export", tags=["Export"])
CSV_FIELDS = (
    "student_id",
    "student_name",
    "student_email",
    "session_date",
    "session_name",
    "status",
    "checked_in_at",
    "risk_score",
)


def _authorize_course_export(
    db: Session, user: Dict[str, Any], course_id: str
) -> CourseModel:
    role = user.get("role")
    if role not in {"instructor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or Admin permissions required.",
        )
    course = db.query(CourseModel).filter(CourseModel.id == course_id).first()
    if course is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found.",
        )
    if role == "instructor":
        require_course_staff_access(db, user, course_id)
    return course


def _render_csv(records: list[dict[str, Any]]) -> str:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=CSV_FIELDS, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(records)
    return output.getvalue()


def _log_export(
    db: Session,
    request: Request,
    user: Dict[str, Any],
    resource_id: str,
    resource_type: str,
) -> None:
    add_audit_log(
        db,
        request,
        "data_exported",
        user_id=str(user["id"]),
        resource_type=resource_type,
        resource_id=resource_id,
    )
    db.commit()


def _as_date(value: Optional[datetime]) -> Optional[str]:
    return value.date().isoformat() if value else None


@router.get("/attendance/{course_id}", status_code=status.HTTP_200_OK)
def export_course_attendance(
    course_id: str,
    request: Request,
    format: str = Query("csv", pattern="^(csv|json)$"),
    start_date: Optional[date] = Query(None),
    end_date: Optional[date] = Query(None),
    user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _authorize_course_export(db, user, course_id)
    session_query = db.query(SessionModel).filter(SessionModel.course_id == course_id)
    if start_date:
        session_query = session_query.filter(
            SessionModel.scheduled_start >= datetime.combine(start_date, time.min)
        )
    if end_date:
        session_query = session_query.filter(
            SessionModel.scheduled_start < datetime.combine(
                date.fromordinal(end_date.toordinal() + 1), time.min
            )
        )
    sessions = session_query.order_by(SessionModel.scheduled_start.asc()).all()
    enrollments = (
        db.query(EnrollmentModel, UserModel)
        .join(UserModel, EnrollmentModel.student_id == UserModel.id)
        .filter(
            EnrollmentModel.course_id == course_id,
            EnrollmentModel.is_active.is_(True),
        )
        .order_by(UserModel.full_name.asc())
        .all()
    )
    session_ids = [session.id for session in sessions]
    checkins = (
        db.query(CheckinModel)
        .filter(CheckinModel.session_id.in_(session_ids))
        .order_by(CheckinModel.checked_in_at.desc())
        .all()
        if session_ids
        else []
    )
    checkin_by_pair: dict[tuple[str, str], CheckinModel] = {}
    for checkin in checkins:
        checkin_by_pair.setdefault((checkin.student_id, checkin.session_id), checkin)

    records = []
    for session in sessions:
        for _, student in enrollments:
            checkin = checkin_by_pair.get((student.id, session.id))
            records.append(
                {
                    "student_id": student.id,
                    "student_name": student.full_name,
                    "student_email": student.email,
                    "session_date": _as_date(session.scheduled_start),
                    "session_name": session.name,
                    "status": checkin.status if checkin else "absent",
                    "checked_in_at": (
                        checkin.checked_in_at.isoformat() if checkin else ""
                    ),
                    "risk_score": checkin.risk_score if checkin else 0.0,
                }
            )

    _log_export(db, request, user, course_id, "course_attendance")
    if format == "json":
        return records
    return Response(
        content=_render_csv(records),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="course-{course_id}-attendance.csv"'
        },
    )


@router.get("/session/{session_id}", status_code=status.HTTP_200_OK)
def export_session_attendance(
    session_id: str,
    request: Request,
    format: str = Query("csv", pattern="^(csv|json)$"),
    user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    role = user.get("role")
    if role not in {"instructor", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor permissions required.",
        )

    session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Session with ID '{session_id}' not found.",
        )
    if role == "instructor":
        require_course_staff_access(db, user, session.course_id)

    course = db.query(CourseModel).filter(CourseModel.id == session.course_id).first()
    checkins = (
        db.query(CheckinModel, UserModel)
        .join(UserModel, CheckinModel.student_id == UserModel.id)
        .filter(CheckinModel.session_id == session_id)
        .order_by(UserModel.full_name.asc())
        .all()
    )
    records = [
        {
            "student_id": student.id,
            "student_name": student.full_name,
            "student_email": student.email,
            "session_date": _as_date(session.scheduled_start),
            "session_name": session.name,
            "status": checkin.status,
            "checked_in_at": (
                checkin.checked_in_at.isoformat() if checkin.checked_in_at else ""
            ),
            "risk_score": checkin.risk_score or 0.0,
        }
        for checkin, student in checkins
    ]
    total_enrolled = (
        db.query(EnrollmentModel)
        .filter(
            EnrollmentModel.course_id == session.course_id,
            EnrollmentModel.is_active.is_(True),
        )
        .count()
    )
    approved_count = sum(1 for checkin, _ in checkins if checkin.status == "approved")
    summary = {
        "total_enrolled": total_enrolled,
        "attendance_rate": round(approved_count / total_enrolled, 2)
        if total_enrolled
        else 0.0,
        "checked_in": len(checkins),
    }

    _log_export(db, request, user, session_id, "session_attendance")
    if format == "json":
        return {
            "session_id": session_id,
            "session_name": session.name,
            "course_code": course.code if course else "",
            "summary": summary,
            "records": records,
        }

    return Response(
        content=_render_csv(records),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="session-{session_id}-attendance.csv"'
        },
    )
