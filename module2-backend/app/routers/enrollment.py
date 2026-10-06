from sqlalchemy import or_
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func, create_engine
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import declarative_base, Session, relationship, sessionmaker
from security import get_current_user
import os
from dotenv import load_dotenv

# Database model

Base = declarative_base()

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


from models import UserModel as User, CourseModel as Course, EnrollmentModel as Enrollment


# Pydantic Schemas
# =====================================================================

class StudentEnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID
    course_code: str
    course_name: str
    semester: str
    instructor_name: Optional[str] = None
    enrolled_at: datetime
    is_active: bool

class EnrollmentCreate(BaseModel):
    student_id: uuid.UUID
    course_id: uuid.UUID

class BulkEnrollmentRequest(BaseModel):
    course_id: uuid.UUID
    student_emails: List[str]
    create_accounts: bool = False  # If true, create accounts for unknown emails

class BulkEnrollmentDetail(BaseModel):
    email: str
    status: str  # e.g., "enrolled", "already_enrolled", "not_found", "created"

class BulkEnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    enrolled: int
    already_enrolled: int
    not_found: int
    created: int
    details: List[BulkEnrollmentDetail]

class EnrolledStudentDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID  # enrollment_id
    student_id: uuid.UUID
    student_email: str
    student_name: str
    enrolled_at: datetime
    is_active: bool
    face_enrolled: bool

class CourseEnrollmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    course_id: uuid.UUID
    course_code: str
    total_enrolled: int
    students: List[EnrolledStudentDetail]


# =====================================================================
# API Endpoints Router
# =====================================================================

router = APIRouter(prefix="/enrollments", tags=["Enrollments"])

@router.post("/", response_model=StudentEnrollmentResponse, status_code=status.HTTP_201_CREATED)
def create_enrollment(
    payload: EnrollmentCreate,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enroll a student in a course. **Requires auth (instructor for course, or admin).**
    """
    user_role = current_user.get("role")

    if user_role not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or Admin permissions required."
        )

    if user_role == "instructor":
        user_id_str = current_user.get("id") or current_user.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials."
            )
        instructor_id = uuid.UUID(str(user_id_str))

        course_check = db.query(Course).filter(Course.id == payload.course_id).first()
        if not course_check or course_check.instructor_id != instructor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not the instructor for this course."
            )

    student = db.query(User).filter(User.id == payload.student_id).first()
    course = db.query(Course).filter(Course.id == payload.course_id).first()

    if not student or not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Student or course not found."
        )

    existing_enrollment = (
        db.query(Enrollment)
        .filter(
            Enrollment.student_id == payload.student_id,
            Enrollment.course_id == payload.course_id
        )
        .first()
    )
    if existing_enrollment:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Student already enrolled."
        )

    new_enrollment = Enrollment(
        student_id=payload.student_id,
        course_id=payload.course_id,
        is_active=True
    )
    db.add(new_enrollment)
    db.commit()
    db.refresh(new_enrollment)

    instructor_name = course.instructor.full_name if course.instructor else None

    return StudentEnrollmentResponse(
        id=new_enrollment.id,
        course_id=course.id,
        course_code=course.code,
        course_name=course.name,
        semester=course.semester,
        instructor_name=instructor_name,
        enrolled_at=new_enrollment.enrolled_at,
        is_active=new_enrollment.is_active
    )

@router.post("/bulk", response_model=BulkEnrollmentResponse, status_code=status.HTTP_200_OK)
def bulk_enroll_students(
    payload: BulkEnrollmentRequest,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Bulk enroll students by email. **Requires auth (instructor for course, or admin).**
    """
    user_role = current_user.get("role")

    if user_role not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or Admin permissions required."
        )

    # Verify Course Exists
    course = db.query(Course).filter(Course.id == payload.course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{payload.course_id}' not found."
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

    enrolled_count = 0
    already_enrolled_count = 0
    not_found_count = 0
    created_count = 0
    details = []

    for email in payload.student_emails:
        clean_email = email.strip().lower()
        student = db.query(User).filter(func.lower(User.email) == clean_email).first()

        if not student:
            if payload.create_accounts:
                # Optional: create a placeholder account for unknown emails
                # Extract a readable default name from the email prefix
                default_name = clean_email.split('@')[0].replace('.', ' ').title()
                student = User(full_name=default_name, email=clean_email)
                db.add(student)
                db.commit()
                db.refresh(student)
                created_count += 1
            else:
                not_found_count += 1
                details.append(BulkEnrollmentDetail(email=email, status="not_found"))
                continue

        # Check if already enrolled in the course
        existing_enrollment = (
            db.query(Enrollment)
            .filter(
                Enrollment.student_id == student.id,
                Enrollment.course_id == payload.course_id
            )
            .first()
        )

        if existing_enrollment:
            # If previously inactive, we can reactivate or mark as already_enrolled
            if not existing_enrollment.is_active:
                existing_enrollment.is_active = True
                db.commit()
                enrolled_count += 1
                details.append(BulkEnrollmentDetail(email=email, status="enrolled"))
            else:
                already_enrolled_count += 1
                details.append(BulkEnrollmentDetail(email=email, status="already_enrolled"))
        else:
            new_enrollment = Enrollment(
                student_id=student.id,
                course_id=payload.course_id,
                is_active=True
            )
            db.add(new_enrollment)
            db.commit()
            enrolled_count += 1
            status_label = "created" if (not student and payload.create_accounts) else "enrolled"
            details.append(BulkEnrollmentDetail(email=email, status="enrolled"))

    return BulkEnrollmentResponse(
        enrolled=enrolled_count,
        already_enrolled=already_enrolled_count,
        not_found=not_found_count,
        created=created_count,
        details=details
    )

@router.get("/my-enrollments", response_model=List[StudentEnrollmentResponse], status_code=status.HTTP_200_OK)
def get_my_enrollments(
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") != "student":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Student permissions required."
        )

    user_id_str = current_user.get("id") or current_user.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials."
        )

    student_id = uuid.UUID(str(user_id_str))

    enrollments = (
        db.query(Enrollment)
        .join(Enrollment.course)
        .outerjoin(Course.instructor)
        .filter(Enrollment.student_id == student_id)
        .order_by(Enrollment.enrolled_at.desc())
        .all()
    )

    response_data = []
    for enr in enrollments:
        c = enr.course
        instructor_name = c.instructor.full_name if c and c.instructor else None

        response_data.append(
            StudentEnrollmentResponse(
                id=enr.id,
                course_id=c.id,
                course_code=c.code,
                course_name=c.name,
                semester=c.semester,
                instructor_name=instructor_name,
                enrolled_at=enr.enrolled_at,
                is_active=enr.is_active
            )
        )

    return response_data

@router.get("/course/{course_id}", response_model=CourseEnrollmentResponse, status_code=status.HTTP_200_OK)
def get_course_enrollments(
    course_id: uuid.UUID,
    is_active: Optional[bool] = Query(True, description="Filter by enrollment status"),
    search: Optional[str] = Query(None, description="Search by student name or email"),
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.get("role") not in ["instructor", "ta", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or TA permissions required."
        )

    course = db.query(Course).filter(Course.id == course_id).first()
    if not course:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Course with ID '{course_id}' not found."
        )

    query = (
        db.query(Enrollment)
        .join(Enrollment.student)
        .filter(Enrollment.course_id == course_id)
    )

    if is_active is not None:
        query = query.filter(Enrollment.is_active == is_active)

    if search:
        search_pattern = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(search_pattern),
                User.email.ilike(search_pattern)
            )
        )

    enrollments = query.order_by(User.full_name.asc()).all()

    students_data = [
        EnrolledStudentDetail(
            id=enr.id,
            student_id=enr.student.id,
            student_email=enr.student.email,
            student_name=enr.student.full_name,
            enrolled_at=enr.enrolled_at,
            is_active=enr.is_active,
            face_enrolled=getattr(enr.student, "face_enrolled", False)
        )
        for enr in enrollments if enr.student
    ]

    return CourseEnrollmentResponse(
        course_id=course.id,
        course_code=course.code,
        total_enrolled=len(students_data),
        students=students_data
    )

@router.delete("/{enrollment_id}", status_code=status.HTTP_200_OK)
def delete_enrollment(
    enrollment_id: uuid.UUID,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    user_role = current_user.get("role")

    if user_role not in ["instructor", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Instructor or Admin permissions required."
        )

    enrollment = db.query(Enrollment).filter(Enrollment.id == enrollment_id).first()
    if not enrollment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Enrollment with ID '{enrollment_id}' not found."
        )

    if user_role == "instructor":
        user_id_str = current_user.get("id") or current_user.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials."
            )
        instructor_id = uuid.UUID(str(user_id_str))

        course = db.query(Course).filter(Course.id == enrollment.course_id).first()
        if not course or course.instructor_id != instructor_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You are not the instructor for this course."
            )

    db.delete(enrollment)
    db.commit()

    return {"detail": f"Enrollment with ID '{enrollment_id}' successfully removed."}