import os
import csv
import io
import uuid
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, String, Boolean, DateTime, Date, Float, ForeignKey, func, create_engine, or_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, Session, sessionmaker, relationship
from security import get_current_user

# Environment Configuration & Database Setup
# =====================================================================

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


# Database Models (including imports)

from models import UserModel as User, CourseModel as Course, SessionModel, EnrollmentModel as Enrollment

class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id = Column(UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False)
    session_name = Column(String(255), nullable=False)
    session_date = Column(Date, nullable=False)

    course = relationship("Course", backref="attendance_sessions")

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = Column(UUID(as_uuid=True), ForeignKey("attendance_sessions.id"), nullable=False)
    student_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    status = Column(String(50), nullable=False)
    checked_in_at = Column(DateTime(timezone=True), nullable=True)
    risk_score = Column(Float, nullable=True, default=0.0)

    session = relationship("AttendanceSession", backref="records")
    student = relationship("User", foreign_keys=[student_id])


# API Endpoints Router
# =====================================================================

router = APIRouter(prefix="/export", tags=["Export"])


@router.get("/export/attendance/{course_id}", status_code=status.HTTP_200_OK)
def export_course_attendance(
    course_id: uuid.UUID,
    format: str = Query("csv", pattern="^(csv|json)$", description="Export format (csv|json)"),
    start_date: Optional[date] = Query(None, description="Start date (ISO8601)"),
    end_date: Optional[date] = Query(None, description="End date (ISO8601)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export attendance data for a course. **Requires auth (instructor for course, or admin).**
    """
    user_role = current_user.get("role")
    if user_role not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or Admin permissions required."
        )

    course_id_str = str(course_id)
    course = db.query(Course).filter(Course.id == course_id_str).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )

    if user_role == "instructor":
        user_id_str = current_user.get("id") or current_user.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials."
            )
        
        instructor_session = db.query(SessionModel).filter(
            SessionModel.course_id == course_id_str,
            SessionModel.instructor_id == str(user_id_str)
        ).first()

        if not instructor_session:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not the instructor for this course."
            )

    # Query attendance records by joining Sessions, Users (Students), and Check-ins/Attendance records
    # Adjust model names depending on your exact attendance tracking schema tables
    attendance_query = (
        db.query(
            User.id.label("student_id"),
            User.full_name.label("student_name"),
            User.email.label("student_email"),
            SessionModel.scheduled_start.label("session_date"),
            SessionModel.name.label("session_name"),
            # Add status, checked_in_at, risk_score from your check-in/attendance table model
        )
        .join(SessionModel, SessionModel.course_id == course_id_str)
        # .join(AttendanceModel, AttendanceModel.session_id == SessionModel.id)
        # .join(User, User.id == AttendanceModel.student_id)
    )

    if start_date:
        attendance_query = attendance_query.filter(SessionModel.scheduled_start >= start_date)
    if end_date:
        attendance_query = attendance_query.filter(SessionModel.scheduled_start <= end_date)

    records = attendance_query.all()

    if format == "json":
        # Return serialized JSON array
        return [
            {
                "student_id": r.student_id,
                "student_name": r.student_name,
                "student_email": r.student_email,
                "session_date": r.session_date,
                "session_name": r.session_name,
                "status": getattr(r, "status", "absent"),
                "checked_in_at": getattr(r, "checked_in_at", None),
                "risk_score": getattr(r, "risk_score", 0.0)
            }
            for r in records
        ]

    # CSV Export format
    output = io.StringIO()
    writer = csv.writer(output)
    
    # CSV Header columns
    writer.writerow([
        "student_id", "student_name", "student_email", 
        "session_date", "session_name", "status", 
        "checked_in_at", "risk_score"
    ])
    
    for r in records:
        writer.writerow([
            r.student_id,
            r.student_name,
            r.student_email,
            r.session_date,
            r.session_name,
            getattr(r, "status", "absent"),
            getattr(r, "checked_in_at", ""),
            getattr(r, "risk_score", 0.0)
        ])

    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=course_{course_id}_attendance.csv"}
    )


@router.get("/session/{session_id}", status_code=status.HTTP_200_OK)
def export_session_attendance(
    session_id: uuid.UUID,
    format: str = Query("csv", pattern="^(csv|json)$", description="Export format (csv|json)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export check-in data for a session. **Requires auth (instructor for session, or admin).**
    """
    user_role = current_user.get("role")
    if user_role not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor permissions required."
        )

    session_id_str = str(session_id)
    # Fetch session using SessionModel (or your project's correct session model name)
    session_obj = db.query(SessionModel).filter(SessionModel.id == session_id_str).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance session with ID '{session_id}' not found."
        )

    if user_role == "instructor":
        user_id_str = current_user.get("id") or current_user.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials."
            )
        
        # Verify instructor ownership directly via SessionModel since Course lacks instructor_id
        if session_obj.instructor_id != str(user_id_str):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not the instructor for this session."
            )

    # Query attendance records for the specific session
    results = (
        db.query(AttendanceRecord, User)
        .join(User, AttendanceRecord.student_id == User.id)
        .filter(AttendanceRecord.session_id == session_id_str)
        .order_by(User.full_name.asc())
        .all()
    )

    export_rows = []
    for record, student in results:
        export_rows.append(
            {
                "student_id": student.id,
                "student_name": student.full_name,
                "student_email": student.email,
                "session_date": session_obj.scheduled_start.isoformat() if session_obj.scheduled_start else "",
                "session_name": session_obj.name,
                "status": record.status,
                "checked_in_at": record.checked_in_at.isoformat() if record.checked_in_at else "",
                "risk_score": record.risk_score if record.risk_score is not None else 0.0
            }
        )

    if format.lower() == "json":
        return export_rows

    output = io.StringIO()
    writer = csv.writer(output)

    writer.writerow([
        "student_id",
        "student_name",
        "student_email",
        "session_date",
        "session_name",
        "status",
        "checked_in_at",
        "risk_score"
    ])

    for row in export_rows:
        writer.writerow([
            row["student_id"],
            row["student_name"],
            row["student_email"],
            row["session_date"],
            row["session_name"],
            row["status"],
            row["checked_in_at"],
            row["risk_score"]
        ])

    output.seek(0)
    session_date_str = session_obj.scheduled_start.isoformat() if session_obj.scheduled_start else "session"
    filename = f"session_export_{session_date_str}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )