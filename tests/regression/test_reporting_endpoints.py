import csv
import io
import uuid

import pytest


def test_statistics_and_exports_use_database_records(
    client,
    test_course,
    test_session,
    test_enrollment,
    auth_headers_instructor,
    auth_headers_admin,
):
    session_stats = client.get(
        f"/api/v1/stats/sessions/{test_session['id']}",
        headers=auth_headers_instructor,
    )
    assert session_stats.status_code == 200, session_stats.text
    session_data = session_stats.json()
    assert session_data["session_name"] == test_session["name"]
    assert session_data["total_enrolled"] == 1
    assert session_data["checked_in_count"] == 0

    course_stats = client.get(
        f"/api/v1/stats/courses/{test_course['id']}",
        headers=auth_headers_instructor,
    )
    assert course_stats.status_code == 200, course_stats.text
    course_data = course_stats.json()
    assert course_data["course_code"] == test_course["code"]
    assert course_data["total_enrolled"] == 1
    assert any(
        session["session_id"] == test_session["id"]
        for session in course_data["sessions"]
    )

    filtered_course_stats = client.get(
        f"/api/v1/stats/courses/{test_course['id']}",
        params={
            "start_date": "2000-01-01T00:00:00Z",
            "end_date": "2001-01-01T00:00:00Z",
        },
        headers=auth_headers_instructor,
    )
    assert filtered_course_stats.status_code == 200, filtered_course_stats.text
    assert filtered_course_stats.json()["total_sessions"] == 0

    student_stats = client.get(
        f"/api/v1/stats/students/{test_enrollment['student_id']}",
        headers=auth_headers_instructor,
    )
    assert student_stats.status_code == 200, student_stats.text
    student_data = student_stats.json()
    assert student_data["student_email"]
    assert any(
        row["course_id"] == test_course["id"] for row in student_data["courses"]
    )
    assert isinstance(student_data["recent_checkins"], list)

    session_export = client.get(
        f"/api/v1/export/session/{test_session['id']}",
        params={"format": "json"},
        headers=auth_headers_instructor,
    )
    assert session_export.status_code == 200, session_export.text
    session_export_data = session_export.json()
    assert session_export_data["session_id"] == test_session["id"]
    assert session_export_data["summary"] == {
        "total_enrolled": 1,
        "attendance_rate": 0.0,
        "checked_in": 0,
    }
    assert session_export_data["records"] == []

    course_export = client.get(
        f"/api/v1/export/attendance/{test_course['id']}",
        params={"format": "json"},
        headers=auth_headers_instructor,
    )
    assert course_export.status_code == 200, course_export.text
    course_records = course_export.json()
    exported_test_session = next(
        record
        for record in course_records
        if record["session_name"] == test_session["name"]
    )
    assert exported_test_session["student_id"] == test_enrollment["student_id"]
    assert exported_test_session["status"] == "absent"

    audit_logs = client.get(
        "/api/v1/audit/",
        params={"resource_type": "session_attendance"},
        headers=auth_headers_admin,
    )
    assert audit_logs.status_code == 200, audit_logs.text
    assert any(
        item["action"] == "data_exported"
        and item["resource_id"] == test_session["id"]
        for item in audit_logs.json()["items"]
    )

    csv_export = client.get(
        f"/api/v1/export/session/{test_session['id']}",
        headers=auth_headers_instructor,
    )
    assert csv_export.status_code == 200
    reader = csv.DictReader(io.StringIO(csv_export.text))
    assert "student_email" in reader.fieldnames
    assert list(reader) == []


@pytest.mark.parametrize("path", ["stats/sessions", "export/session"])
def test_reporting_rejects_unknown_sessions(client, auth_headers_instructor, path):
    response = client.get(
        f"/api/v1/{path}/{uuid.uuid4()}", headers=auth_headers_instructor,
    )
    assert response.status_code == 404


def test_reporting_rejects_unassigned_instructor(client, test_session, unique_email):
    email = unique_email()
    registration = client.post("/api/v1/auth/register", json={
        "email": email,
        "password": "reporting-test-password",
        "full_name": "Unassigned instructor",
        "role": "instructor",
    })
    assert registration.status_code == 201
    login = client.post("/api/v1/auth/login", json={
        "email": email, "password": "reporting-test-password",
    })
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    for path in ("stats/sessions", "export/session"):
        response = client.get(
            f"/api/v1/{path}/{test_session['id']}", headers=headers,
        )
        assert response.status_code == 403


def test_audit_summary_counts_persisted_events(client, auth_headers_admin):
    before = client.get("/api/v1/audit/summary", headers=auth_headers_admin)
    assert before.status_code == 200
    created = client.post("/api/v1/audit/logs", headers=auth_headers_admin, json={
        "action": "data_exported", "resource_type": "reporting_regression",
    })
    assert created.status_code == 201
    after = client.get("/api/v1/audit/summary", headers=auth_headers_admin)
    assert after.status_code == 200
    assert after.json()["by_action"]["data_exported"] > before.json()["by_action"].get("data_exported", 0)
    assert after.json()["total_logs"] == sum(after.json()["by_action"].values())
    invalid = client.get("/api/v1/audit/summary?days=0", headers=auth_headers_admin)
    assert invalid.status_code == 422
