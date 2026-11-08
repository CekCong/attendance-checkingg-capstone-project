"""CSV rosters and matriculation identity, using isolated DBs and namespaced Redis."""
import uuid

import pytest
from sqlalchemy import create_engine, inspect, text

from test_auth_migration import auth_app
from test_security_privacy_migration import headers
from app.models import CourseRosterModel, EnrollmentModel, UserModel, Base
from app.routers import course_rosters, courses, enrollment, users
from app.migrate import migrate


@pytest.fixture
def roster_app(auth_app):
    http, db, student, _, _ = auth_app
    for router in (course_rosters.router, courses.router, enrollment.router, users.router):
        http.app.include_router(router, prefix="/api/v1")
    teacher = UserModel(id=str(uuid.uuid4()), email="roster-teacher@example.com", full_name="Teacher", role="instructor", hashed_password="unused")
    outsider = UserModel(id=str(uuid.uuid4()), email="roster-other@example.com", full_name="Other", role="instructor", hashed_password="unused")
    admin = UserModel(id=str(uuid.uuid4()), email="roster-admin@example.com", full_name="Admin", role="admin", hashed_password="unused")
    student.matriculation_number = "U000001A"
    db.add_all([teacher, outsider, admin]); db.commit()
    created = http.post("/api/v1/courses/", headers=headers(admin), json={"code": "CSV101", "name": "CSV Course", "semester": "2026/27 Semester 1", "instructor_id": teacher.id})
    assert created.status_code == 201, created.text
    return http, db, student, teacher, outsider, created.json()["id"]


def upload(fixture, content, preview=False, actor=None):
    http, _, _, teacher, _, course_id = fixture
    return http.post(f"/api/v1/enrollments/course/{course_id}/csv?preview={str(preview).lower()}",
                     headers={**headers(actor or teacher), "Content-Type": "text/csv"}, content=content)


def test_preview_is_read_only_and_import_is_idempotent(roster_app):
    http, db, student, teacher, _, course_id = roster_app
    csv = "\ufeffmatriculation_number,full_name\r\n u000001a ,Known\r\nU000002B,Pending\r\nu000001a,Duplicate\r\n"
    preview = upload(roster_app, csv.encode("utf-8"), preview=True)
    assert preview.status_code == 200, preview.text
    assert preview.json()["enrolled"] == 1 and preview.json()["pending"] == 1
    assert preview.json()["duplicates"] == 1
    assert db.query(CourseRosterModel).count() == db.query(EnrollmentModel).count() == 0
    imported = upload(roster_app, csv.encode("utf-8"))
    assert imported.status_code == 200, imported.text
    assert db.query(CourseRosterModel).count() == 2
    assert db.query(EnrollmentModel).filter_by(student_id=student.id, course_id=course_id, is_active=True).count() == 1
    again = upload(roster_app, csv.encode("utf-8"))
    assert again.json()["enrolled"] == 0 and again.json()["already_enrolled"] == 1
    assert db.query(EnrollmentModel).count() == 1
    roster = http.get(f"/api/v1/enrollments/course/{course_id}/roster", headers=headers(teacher)).json()
    assert [row["status"] for row in roster["items"]] == ["already_enrolled", "pending"]


def test_pending_number_enrolls_on_signup_and_is_in_account_and_course_list(roster_app):
    http, db, _, _, _, course_id = roster_app
    assert upload(roster_app, b"matriculation_number\n000123\n").status_code == 200
    response = http.post("/api/v1/auth/register", json={"email": "new-student@example.com", "password": "Valid-password-123",
                        "full_name": "New Student", "matriculation_number": " 000123 "})
    assert response.status_code == 201, response.text
    assert response.json()["matriculation_number"] == "000123"
    student = db.get(UserModel, response.json()["id"])
    profile = http.get("/api/v1/users/me", headers=headers(student))
    assert profile.json()["matriculation_number"] == "000123"
    enrollments = http.get("/api/v1/enrollments/my-enrollments", headers=headers(student))
    assert enrollments.status_code == 200, enrollments.text
    assert enrollments.json()[0]["course_id"] == course_id


def test_existing_student_links_once_and_duplicate_claims_are_rejected(roster_app):
    http, db, student, teacher, _, course_id = roster_app
    student.matriculation_number = None; db.commit()
    assert upload(roster_app, b"matric_no\nU000005E\n").status_code == 200
    response = http.put("/api/v1/users/me", headers=headers(student), json={"matriculation_number": "u000005e"})
    assert response.status_code == 200, response.text
    assert response.json()["matriculation_number"] == "U000005E"
    assert db.query(EnrollmentModel).filter_by(course_id=course_id).count() == 1
    assert http.put("/api/v1/users/me", headers=headers(student), json={"matriculation_number": "U000006F"}).status_code == 409
    assert http.put("/api/v1/users/me", headers=headers(student), json={"matriculation_number": None}).status_code == 409
    assert http.put("/api/v1/users/me", headers=headers(teacher), json={"matriculation_number": "U000006F"}).status_code == 403
    duplicate = http.post("/api/v1/auth/register", json={"email": "duplicate@example.com", "password": "Valid-password-123",
                         "full_name": "Duplicate", "matriculation_number": "u000005e"})
    assert duplicate.status_code == 409, duplicate.text
    db.rollback()  # Dependency teardown rolls back in the running app; fixture shares one Session.
    assert db.query(UserModel).filter_by(email="duplicate@example.com").count() == 0


@pytest.mark.parametrize("csv", [
    b"email\na@example.com\n", b"matriculation_number\n", b"matriculation_number\nU000001A\n!bad\n",
    b"matriculation_number\nU000001A,extra\n", b'matriculation_number\n"unclosed', b"\xff\xfeinvalid",
    b"matriculation_number,matric_no\nU000001A,U000001A\n",
    b"matriculation_number\n" + b"U000001A\n" * 1001,
])
def test_invalid_roster_rejects_whole_file(roster_app, csv):
    _, db, *_ = roster_app
    response = upload(roster_app, csv)
    assert response.status_code == 422, response.text
    assert db.query(CourseRosterModel).count() == db.query(EnrollmentModel).count() == 0


def test_permissions_size_limit_and_inactive_account(roster_app):
    http, db, student, teacher, outsider, course_id = roster_app
    csv = b"matriculation_number\nU000001A\n"
    for actor in (student, outsider):
        assert upload(roster_app, csv, actor=actor).status_code == 403
        assert http.get(f"/api/v1/enrollments/course/{course_id}/roster", headers=headers(actor)).status_code == 403
    assert http.post(f"/api/v1/enrollments/course/{course_id}/csv", content=csv).status_code == 401
    assert upload(roster_app, b"a" * 1_000_001).status_code == 413
    student.is_active = False; db.commit()
    assert upload(roster_app, csv).status_code == 409
    assert db.query(CourseRosterModel).count() == 0


def test_reimport_can_reactivate_but_profile_save_does_not_undo_unenrollment(roster_app):
    http, db, student, _, _, course_id = roster_app
    csv = b"matriculation_number\nU000001A\n"
    upload(roster_app, csv)
    enrolled = db.query(EnrollmentModel).one()
    enrolled.is_active = False; db.commit()
    assert http.put("/api/v1/users/me", headers=headers(student), json={"full_name": "Updated"}).status_code == 200
    assert not db.get(EnrollmentModel, enrolled.id).is_active
    assert upload(roster_app, csv).json()["enrolled"] == 1
    assert db.query(EnrollmentModel).filter_by(course_id=course_id, is_active=True).count() == 1


def test_migration_preserves_legacy_users_and_is_repeatable(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(text("DROP INDEX uq_users_matriculation_number"))
        connection.execute(text("ALTER TABLE users DROP COLUMN matriculation_number"))
        connection.execute(text("INSERT INTO users (id,email,full_name,hashed_password,role,is_active,failed_login_attempts) VALUES ('legacy','legacy@example.com','Legacy','unused','student',1,0)"))
    migrate(engine); migrate(engine)
    with engine.connect() as connection:
        assert connection.execute(text("SELECT matriculation_number FROM users WHERE id='legacy'")).scalar() is None
        assert any(index["name"] == "uq_users_matriculation_number" and index["unique"] for index in inspect(connection).get_indexes("users"))
    engine.dispose()
