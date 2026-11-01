"""Preview and import additive course rosters without creating placeholder accounts."""
import csv
import io

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CourseModel, CourseRosterModel, EnrollmentModel, UserModel
from app.security import require_roles
from app.course_access import require_course_staff_access
from app.roster import activate_enrollment, lock_roster_updates, normalize_matriculation
from app.audit import add_audit_log

router = APIRouter(prefix="/enrollments", tags=["Course rosters"])
MAX_BYTES = 1_000_000
MAX_ROWS = 1000
HEADERS = {"matriculation_number", "matriculation_no", "matric_number", "matric_no"}


def read_csv(content):
    try:
        reader = csv.reader(io.StringIO(content.decode("utf-8-sig")), strict=True)
        headers = next(reader, [])
        normalized = [h.strip().lower().replace(" ", "_").replace("-", "_") for h in headers]
        columns = [i for i, h in enumerate(normalized) if h in HEADERS]
        if len(columns) != 1:
            raise HTTPException(422, "CSV must have exactly one matriculation_number column. Download the template.")
        numbers, errors, seen, duplicates = [], [], set(), 0
        for line, row in enumerate(reader, 2):
            if not any(value.strip() for value in row):
                continue
            if line > MAX_ROWS + 1:
                raise HTTPException(422, "Upload at most 1,000 rows per CSV.")
            try:
                if len(row) != len(headers):
                    raise ValueError("Number of columns does not match the header.")
                number = normalize_matriculation(row[columns[0]])
                if number in seen:
                    duplicates += 1
                else:
                    seen.add(number)
                    numbers.append(number)
            except ValueError as exc:
                errors.append({"row": line, "message": str(exc)})
        if errors:
            raise HTTPException(422, {"message": "Fix the CSV rows below. No students were imported.", "rows": errors[:25]})
        if not numbers:
            raise HTTPException(422, "CSV has no student rows.")
        return numbers, duplicates
    except (UnicodeDecodeError, csv.Error) as exc:
        raise HTTPException(422, "Upload a valid UTF-8 CSV file, not an Excel workbook.") from exc


def course_access(db, user, course_id):
    course = db.get(CourseModel, course_id)
    if not course or not course.is_active:
        raise HTTPException(404, "Active course not found.")
    require_course_staff_access(db, user, course_id)


def roster_rows(db, course_id, numbers):
    users = {user.matriculation_number: user for user in db.query(UserModel)
             .filter(UserModel.matriculation_number.in_(numbers)).all()}
    enrolled = {row.student_id: row for row in db.query(EnrollmentModel)
                .filter(EnrollmentModel.course_id == course_id).all()}
    rows = []
    for number in numbers:
        user = users.get(number)
        enrollment = enrolled.get(user.id) if user else None
        state = "pending" if not user else "blocked" if user.role != "student" or not user.is_active else (
            "already_enrolled" if enrollment and enrollment.is_active else "enroll")
        rows.append({"matriculation_number": number, "name": user.full_name if user else None, "status": state})
    return rows, users, enrolled


@router.get("/course/{course_id}/roster")
def get_roster(course_id: str, response: Response, user=Depends(require_roles("instructor", "admin")), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    course_access(db, user, course_id)
    numbers = [row[0] for row in db.query(CourseRosterModel.matriculation_number)
               .filter(CourseRosterModel.course_id == course_id).order_by(CourseRosterModel.matriculation_number).all()]
    rows, _, _ = roster_rows(db, course_id, numbers)
    return {"items": rows, "total": len(rows)}


@router.post("/course/{course_id}/csv")
async def import_roster(course_id: str, request: Request, response: Response, preview: bool = Query(True),
                        user=Depends(require_roles("instructor", "admin")), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    course_access(db, user, course_id)
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_BYTES:
            raise HTTPException(413, "CSV must be smaller than 1 MB.")
    numbers, duplicates = read_csv(content)
    if not preview:
        lock_roster_updates(db)
    rows, users, enrolled = roster_rows(db, course_id, numbers)
    if any(row["status"] == "blocked" for row in rows):
        raise HTTPException(409, "The roster includes an inactive or non-student account. Ask an administrator to resolve it. No rows were imported.")
    if not preview:
        existing = {row[0] for row in db.query(CourseRosterModel.matriculation_number)
                    .filter(CourseRosterModel.course_id == course_id).all()}
        for row in rows:
            number = row["matriculation_number"]
            if number not in existing:
                db.add(CourseRosterModel(course_id=course_id, matriculation_number=number))
            if row["status"] == "enroll":
                student = users[number]
                activate_enrollment(db, request, user["id"], student.id, course_id, enrolled.get(student.id))
        add_audit_log(db, request, "enrollment_added", user_id=user["id"], resource_type="course", resource_id=course_id,
                      details=f"CSV roster imported; unique_rows={len(rows)}; pending={sum(row['status'] == 'pending' for row in rows)}")
        db.commit()
    return {"preview": preview, "total": len(rows), "duplicates": duplicates,
            "enrolled": sum(row["status"] == "enroll" for row in rows),
            "already_enrolled": sum(row["status"] == "already_enrolled" for row in rows),
            "pending": sum(row["status"] == "pending" for row in rows), "items": rows}
