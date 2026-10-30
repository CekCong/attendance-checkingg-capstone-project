from typing import Any, Dict, List

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from .models import CourseInstructorModel, EnrollmentModel, SessionModel


def staff_course_ids(db: Session, user: Dict[str, Any]) -> List[str]:
    user_id = str(user.get("id") or "")
    role = user.get("role")

    assigned_courses = {
        course_id
        for (course_id,) in db.query(SessionModel.course_id)
        .filter(SessionModel.instructor_id == user_id)
        .all()
    }
    assigned_courses.update(
        course_id
        for (course_id,) in db.query(CourseInstructorModel.course_id)
        .filter(CourseInstructorModel.instructor_id == user_id)
        .all()
    )

    if role == "ta":
        enrolled_courses = {
            course_id
            for (course_id,) in db.query(EnrollmentModel.course_id)
            .filter(
                EnrollmentModel.student_id == user_id,
                EnrollmentModel.is_active.is_(True),
            )
            .all()
        }
        assigned_courses.update(enrolled_courses)

    return list(assigned_courses)


def require_course_staff_access(
    db: Session,
    user: Dict[str, Any],
    course_id: str,
) -> None:
    if user.get("role") == "admin":
        return
    if user.get("role") not in {"instructor", "ta"} or course_id not in staff_course_ids(db, user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. You are not assigned to this course.",
        )
