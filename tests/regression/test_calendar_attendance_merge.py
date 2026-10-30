"""Calendar and invitation integration with Hongyu's security and reporting stack."""
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from test_stage6_auth_qr import qr_session
from test_security_privacy_migration import attendance, headers
from test_auth_migration import auth_app
from app.models import CourseInstructorModel, CourseModel, SessionModel, SessionOccurrenceModel, SessionSeriesModel, CheckinModel, EnrollmentModel
from app.routers import attendance_codes, courses, recurring_sessions


@pytest.fixture
def calendar_app(qr_session):
    http, db, student, lesson, body, teacher, outsider = qr_session
    for router in (attendance_codes.router, courses.router, recurring_sessions.router):
        http.app.include_router(router, prefix="/api/v1")
    db.execute(text("PRAGMA foreign_keys=ON"))
    db.add(CourseInstructorModel(course_id=lesson.course_id, instructor_id=teacher.id))
    db.commit()
    return qr_session


@pytest.mark.parametrize("when", ["future", "past", "closed", "cancelled"])
def test_demo_invitation_accepts_verified_attendance_at_any_time(calendar_app, monkeypatch, when):
    http, db, student, lesson, body, teacher, outsider = calendar_app
    monkeypatch.setenv("ATTENDANCE_DEMO_MODE", "true")
    if when in {"future", "past"}:
        lesson.scheduled_start = datetime.utcnow() + timedelta(days=7 if when == "future" else -7)
        lesson.scheduled_end = lesson.scheduled_start + timedelta(hours=1)
    else:
        lesson.status = when
    db.commit()
    path = f"/api/v1/sessions/{lesson.id}/attendance-code"
    assert http.post(path, headers=headers(outsider), json={"student_url": "https://students.example.edu"}).status_code == 403
    issued = http.post(path, headers=headers(teacher), json={"student_url": "https://students.example.edu"})
    assert issued.status_code == 200, issued.text
    code = issued.json()
    assert code["open"] and code["demo_mode"] and "<svg" in code["qr_svg"]
    resolved = http.post("/api/v1/attendance/resolve", headers=headers(student), json={"code": code["passcode"]})
    assert resolved.status_code == 200, resolved.text
    submitted = http.post("/api/v1/checkins/", headers=headers(student), json={**body, "qr_code": code["passcode"]})
    assert submitted.status_code == 201, submitted.text
    assert db.query(CheckinModel).count() == 1
    # Delete the actual lesson without erasing append-only audit history.
    assert http.delete(f"/api/v1/sessions/{lesson.id}?permanent=true", headers=headers(teacher)).status_code == 204
    assert db.query(CheckinModel).count() == 0


def test_recurrence_deletion_preserves_other_dates_and_course_ownership(calendar_app):
    http, db, student, original, _, teacher, outsider = calendar_app
    course = http.post("/api/v1/courses/", headers=headers(teacher), json={
        "code": "MERGE-" + uuid.uuid4().hex[:8], "name": "Merged course", "semester": "2026/27 Semester 1",
    })
    assert course.status_code == 201, course.text
    course_id = course.json()["id"]
    day = (datetime.utcnow() + timedelta(days=14)).date()
    schedule = {"request_id": str(uuid.uuid4()), "course_id": course_id, "name": "Weekly lab",
                "start_date": str(day), "end_date": str(day + timedelta(days=14)), "weekday": day.weekday(),
                "start_time": "10:00", "end_time": "11:00", "timezone": "Asia/Singapore"}
    response = http.post("/api/v1/sessions/recurring", headers=headers(teacher), json=schedule)
    assert response.status_code == 201, response.text
    rows = response.json()["sessions"]
    assert len(rows) == 3
    path = f"/api/v1/sessions/{rows[0]['id']}?permanent=true"
    assert http.delete(path, headers=headers(outsider)).status_code == 403
    assert http.delete(path, headers=headers(teacher)).status_code == 204
    retry = http.post("/api/v1/sessions/recurring", headers=headers(teacher), json=schedule)
    assert retry.json()["count"] == 2
    assert db.query(SessionOccurrenceModel).count() == 2
    listed = http.get(f"/api/v1/sessions/?course_id={course_id}", headers=headers(teacher))
    assert listed.status_code == 200, listed.text
    assert all(row["series_id"] == response.json()["series_id"] for row in listed.json()["items"])
    path = f"/api/v1/courses/{course_id}?permanent=true"
    for user in (student, outsider):
        assert http.delete(path, headers=headers(user)).status_code == 403
    assert http.delete(path, headers=headers(teacher)).status_code == 204
    assert db.query(SessionOccurrenceModel).count() == 0
    assert db.query(SessionSeriesModel).count() == 0
    assert db.get(CourseModel, course_id) is None
    assert db.get(SessionModel, original.id) is not None
    assert db.query(EnrollmentModel).filter_by(course_id=original.course_id).count() == 1
