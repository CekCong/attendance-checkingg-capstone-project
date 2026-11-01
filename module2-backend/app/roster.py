"""Matriculation identity and roster matching shared by signup, profile and CSV import."""
import re
import uuid

from fastapi import HTTPException
from sqlalchemy import text

from .audit import add_audit_log
from .models import CourseModel, CourseRosterModel, EnrollmentModel, UserModel


def normalize_matriculation(value):
    if value is None:
        return None
    number = value.strip().upper()
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9-]{2,31}", number):
        raise ValueError("Matriculation number must be 3–32 letters, digits or hyphens.")
    return number


def lock_roster_updates(db):
    # Serialize identity links with imports so simultaneous signup/import cannot
    # miss each other's pending roster. Released on transaction commit/rollback.
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(724816032)"))


def activate_enrollment(db, request, actor_id, student_id, course_id, existing=None):
    if existing and existing.is_active:
        return False
    enrollment = existing or EnrollmentModel(id=str(uuid.uuid4()), student_id=student_id, course_id=course_id)
    enrollment.is_active = True
    enrollment.dropped_at = None
    db.add(enrollment)
    add_audit_log(db, request, "enrollment_added", user_id=actor_id, resource_type="enrollment",
                  resource_id=enrollment.id, details=f"course_id={course_id}; source=matriculation_roster")
    return True


def link_matriculation(db, request, user, number):
    number = normalize_matriculation(number)
    if user.role != "student":
        raise HTTPException(403, "Only student accounts can link a matriculation number.")
    if user.matriculation_number == number:
        return
    if user.matriculation_number:
        raise HTTPException(409, "Your matriculation number is already linked. Contact an administrator to correct it.")
    if not number:
        raise HTTPException(422, "Enter your matriculation number.")
    lock_roster_updates(db)
    duplicate = db.query(UserModel.id).filter(UserModel.matriculation_number == number, UserModel.id != user.id).first()
    if duplicate:
        raise HTTPException(409, "This matriculation number is already linked to an account.")
    user.matriculation_number = number
    db.flush()
    course_ids = [row[0] for row in db.query(CourseRosterModel.course_id).join(CourseModel)
                  .filter(CourseRosterModel.matriculation_number == number, CourseModel.is_active.is_(True)).all()]
    existing = {row.course_id: row for row in db.query(EnrollmentModel)
                .filter(EnrollmentModel.student_id == user.id, EnrollmentModel.course_id.in_(course_ids)).all()}
    for course_id in course_ids:
        activate_enrollment(db, request, user.id, user.id, course_id, existing.get(course_id))
