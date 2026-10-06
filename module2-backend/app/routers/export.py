import os
import csv
import io
import uuid
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import Column, String, Boolean, DateTime, Date, Float, ForeignKey, func, create_engine, or_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, Session, sessionmaker, relationship

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


# Database Models
# =====================================================================

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
    semester = Column(String(50), nullable=False)
    instructor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    instructor = relationship("User", foreign_keys=[instructor_id])

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

@router.get("/attendance/{course_id}", status_code=status.HTTP_200_OK)
def export_course_attendance(
    course_id: uuid.UUID,
    format: str = Query("csv", regex="^(csv|json)$", description="Export format (csv|json)"),
    start_date: Optional[date] = Query(None, description="Start date (ISO8601)"),
    end_date: Optional[date] = Query(None, description="End date (ISO8601)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export attendance data for a course. **Requires auth (instructor for course, or admin).**[cite: 4]
    """
    user_role = current_user.get("role")
    if user_role not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor permissions required."
        )

    course = db.query(Course).filter(Course.id == course_id).first()
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
        instructor_id = uuid.UUID(str(user_id_str))
        if course.instructor_id != instructor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not the instructor for this course."
            )

    effective_start_date = start_date or date(2000, 1, 1)
    effective_end_date = end_date or date.today()

    query = (
        db.query(AttendanceRecord, AttendanceSession, User)
        .join(AttendanceSession, AttendanceRecord.session_id == AttendanceSession.id)
        .join(User, AttendanceRecord.student_id == User.id)
        .filter(AttendanceSession.course_id == course_id)
        .filter(AttendanceSession.session_date >= effective_start_date)
        .filter(AttendanceSession.session_date <= effective_end_date)
        .order_by(AttendanceSession.session_date.asc(), User.full_name.asc())
    )

    results = query.all()

    export_rows = []
    for record, session, student in results:
        export_rows.append(
            {
                "student_id": student.id,
                "student_name": student.full_name,
                "student_email": student.email,
                "session_date": session.session_date.isoformat(),
                "session_name": session.session_name,
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
    filename = f"attendance_export_{course.code}_{date.today().isoformat()}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/session/{session_id}", status_code=status.HTTP_200_OK)
def export_session_attendance(
    session_id: uuid.UUID,
    format: str = Query("csv", regex="^(csv|json)$", description="Export format (csv|json)"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Export check-in data for a session. **Requires auth (instructor for session, or admin).**[cite: 5]
    """
    user_role = current_user.get("role")
    if user_role not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor permissions required."
        )

    # Fetch attendance session
    session_obj = db.query(AttendanceSession).filter(AttendanceSession.id == session_id).first()
    if not session_obj:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Attendance session with ID '{session_id}' not found."
        )

    # Fetch corresponding course to verify instructor access
    course = db.query(Course).filter(Course.id == session_obj.course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Associated course not found."
        )

    if user_role == "instructor":
        user_id_str = current_user.get("id") or current_user.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials."
            )
        instructor_id = uuid.UUID(str(user_id_str))
        if course.instructor_id != instructor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not the instructor for this session's course."
            )

    # Query attendance records for the specific session
    results = (
        db.query(AttendanceRecord, User)
        .join(User, AttendanceRecord.student_id == User.id)
        .filter(AttendanceRecord.session_id == session_id)
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
                "session_date": session_obj.session_date.isoformat(),
                "session_name": session_obj.session_name,
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
    filename = f"session_export_{session_obj.session_date.isoformat()}.csv"

    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )