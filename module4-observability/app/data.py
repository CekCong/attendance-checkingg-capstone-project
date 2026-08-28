"""Stub attendance data for the instructor Streamlit dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

_SESSIONS = [
    {
        "id": "ses-cs101-l4",
        "title": "CS101 Lecture 4",
        "course_code": "CS101",
        "status": "live",
        "starts_at": "2026-08-20T09:00:00Z",
        "enrolled": 48,
        "checkins": 41,
        "flagged": 3,
    },
    {
        "id": "ses-cs204-lab",
        "title": "CS204 Lab",
        "course_code": "CS204",
        "status": "live",
        "starts_at": "2026-08-20T14:00:00Z",
        "enrolled": 30,
        "checkins": 22,
        "flagged": 2,
    },
    {
        "id": "ses-cz3002-l2",
        "title": "CZ3002 Lecture 2",
        "course_code": "CZ3002",
        "status": "scheduled",
        "starts_at": "2026-08-20T16:30:00Z",
        "enrolled": 55,
        "checkins": 0,
        "flagged": 0,
    },
]

_FLAGGED = [
    {
        "id": "chk-f1",
        "student_id": "stu-alex",
        "student_name": "Alex Chen",
        "student_email": "alex.chen@e.ntu.edu.sg",
        "session_id": "ses-cs101-l4",
        "session_title": "CS101 Lecture 4",
        "status": "flagged",
        "reason": "Liveness retry",
        "risk_score": 0.62,
        "checked_in_at": "2026-08-20T09:08:12Z",
    },
    {
        "id": "chk-f2",
        "student_id": "stu-priya",
        "student_name": "Priya Shah",
        "student_email": "priya.shah@e.ntu.edu.sg",
        "session_id": "ses-cs101-l4",
        "session_title": "CS101 Lecture 4",
        "status": "flagged",
        "reason": "Geofence edge",
        "risk_score": 0.58,
        "checked_in_at": "2026-08-20T09:11:40Z",
    },
    {
        "id": "chk-f3",
        "student_id": "stu-jordan",
        "student_name": "Jordan Lee",
        "student_email": "jordan.lee@e.ntu.edu.sg",
        "session_id": "ses-cs204-lab",
        "session_title": "CS204 Lab",
        "status": "appealed",
        "reason": "Device mismatch",
        "risk_score": 0.71,
        "checked_in_at": "2026-08-20T14:06:03Z",
    },
    {
        "id": "chk-f4",
        "student_id": "stu-mina",
        "student_name": "Mina Park",
        "student_email": "mina.park@e.ntu.edu.sg",
        "session_id": "ses-cs204-lab",
        "session_title": "CS204 Lab",
        "status": "flagged",
        "reason": "High risk score",
        "risk_score": 0.66,
        "checked_in_at": "2026-08-20T14:12:22Z",
    },
]

_RECORDS = [
    {
        "checkin_id": "chk-a1",
        "student_id": "stu-wei",
        "student_name": "Wei Tan",
        "student_email": "wei.tan@e.ntu.edu.sg",
        "session_id": "ses-cs101-l4",
        "session_name": "CS101 Lecture 4",
        "session_date": "2026-08-20",
        "status": "approved",
        "checked_in_at": "2026-08-20T09:02:11Z",
        "risk_score": 0.18,
        "liveness_score": 0.92,
        "face_match_score": 0.88,
        "latitude": 1.3483,
        "longitude": 103.6831,
    },
    {
        "checkin_id": "chk-a2",
        "student_id": "stu-hana",
        "student_name": "Hana Lim",
        "student_email": "hana.lim@e.ntu.edu.sg",
        "session_id": "ses-cs101-l4",
        "session_name": "CS101 Lecture 4",
        "session_date": "2026-08-20",
        "status": "approved",
        "checked_in_at": "2026-08-20T09:03:44Z",
        "risk_score": 0.22,
        "liveness_score": 0.90,
        "face_match_score": 0.85,
        "latitude": 1.3481,
        "longitude": 103.6834,
    },
    {
        "checkin_id": "chk-f1",
        "student_id": "stu-alex",
        "student_name": "Alex Chen",
        "student_email": "alex.chen@e.ntu.edu.sg",
        "session_id": "ses-cs101-l4",
        "session_name": "CS101 Lecture 4",
        "session_date": "2026-08-20",
        "status": "flagged",
        "checked_in_at": "2026-08-20T09:08:12Z",
        "risk_score": 0.62,
        "liveness_score": 0.51,
        "face_match_score": 0.80,
        "latitude": 1.3479,
        "longitude": 103.6828,
    },
    {
        "checkin_id": "chk-f2",
        "student_id": "stu-priya",
        "student_name": "Priya Shah",
        "student_email": "priya.shah@e.ntu.edu.sg",
        "session_id": "ses-cs101-l4",
        "session_name": "CS101 Lecture 4",
        "session_date": "2026-08-20",
        "status": "flagged",
        "checked_in_at": "2026-08-20T09:11:40Z",
        "risk_score": 0.58,
        "liveness_score": 0.84,
        "face_match_score": 0.79,
        "latitude": 1.3491,
        "longitude": 103.6840,
    },
    {
        "checkin_id": "chk-b1",
        "student_id": "stu-omar",
        "student_name": "Omar Rahman",
        "student_email": "omar.rahman@e.ntu.edu.sg",
        "session_id": "ses-cs204-lab",
        "session_name": "CS204 Lab",
        "session_date": "2026-08-20",
        "status": "approved",
        "checked_in_at": "2026-08-20T14:01:09Z",
        "risk_score": 0.15,
        "liveness_score": 0.94,
        "face_match_score": 0.91,
        "latitude": 1.3484,
        "longitude": 103.6832,
    },
    {
        "checkin_id": "chk-f3",
        "student_id": "stu-jordan",
        "student_name": "Jordan Lee",
        "student_email": "jordan.lee@e.ntu.edu.sg",
        "session_id": "ses-cs204-lab",
        "session_name": "CS204 Lab",
        "session_date": "2026-08-20",
        "status": "appealed",
        "checked_in_at": "2026-08-20T14:06:03Z",
        "risk_score": 0.71,
        "liveness_score": 0.77,
        "face_match_score": 0.61,
        "latitude": 1.3462,
        "longitude": 103.6810,
    },
]


def build_dashboard() -> dict[str, Any]:
    pulse = int(datetime.now(timezone.utc).timestamp() // 30)
    extra = pulse % 4
    sessions = []
    for session in _SESSIONS:
        row = dict(session)
        if row["status"] == "live":
            row["checkins"] = row["checkins"] + extra
        sessions.append(row)

    records = list(_RECORDS)
    flagged = list(_FLAGGED)
    today_checkins = sum(s["checkins"] for s in sessions)
    approved = sum(1 for r in records if r["status"] == "approved")
    approval_rate = round(approved / len(records), 3) if records else 0
    live_sessions = sum(1 for s in sessions if s["status"] == "live")

    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "poll_interval_seconds": 30,
        "today_sessions": sessions,
        "flagged": flagged,
        "records": records,
        "kpis": {
            "today_checkins": today_checkins,
            "flagged_pending": len(flagged),
            "approval_rate": approval_rate,
            "live_sessions": live_sessions,
        },
    }
