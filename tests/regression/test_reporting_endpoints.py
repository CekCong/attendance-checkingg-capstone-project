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
