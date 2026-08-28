"""Instructor observability stubs: stats, check-in queues, and exports."""

from __future__ import annotations

from typing import Literal, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel

from ..security import require_roles

router = APIRouter(tags=["observability"])

STAFF = require_roles("ta", "instructor", "admin")
INSTRUCTOR = require_roles("instructor", "admin")


class SessionCreateBody(BaseModel):
    course_id: Optional[str] = None
    name: Optional[str] = None
    title: Optional[str] = None
    session_type: Optional[str] = None
    scheduled_start: Optional[str] = None
    scheduled_end: Optional[str] = None


class SessionPatchBody(BaseModel):
    name: Optional[str] = None
    status: Optional[str] = None


@router.get("/stats/overview")
async def stats_overview(_user=Depends(INSTRUCTOR)):
    return {
        "total_sessions": 12,
        "active_sessions": 2,
        "total_courses": 4,
        "total_students": 128,
        "today_checkins": 63,
        "flagged_pending": 4,
        "approval_rate": 0.86,
    }


@router.get("/stats/sessions/{session_id}")
async def stats_session(session_id: str, _user=Depends(INSTRUCTOR)):
    return {
        "session_id": session_id,
        "session_name": "CS101 Lecture 4",
        "total_enrolled": 48,
        "checked_in_count": 41,
        "approved_count": 38,
        "flagged_count": 3,
        "attendance_rate": 0.85,
        "average_risk_score": 0.24,
    }


@router.get("/stats/courses/{course_id}")
async def stats_course(course_id: str, _user=Depends(INSTRUCTOR)):
    return {
        "course_id": course_id,
        "course_code": "CS101",
        "total_enrolled": 48,
        "total_sessions": 6,
        "average_attendance_rate": 0.81,
        "flagged_checkins": 5,
    }


@router.get("/stats/students/{student_id}")
async def stats_student(student_id: str, _user=Depends(INSTRUCTOR)):
    return {
        "student_id": student_id,
        "student_name": "Test Student",
        "total_enrolled_courses": 2,
        "total_sessions": 8,
        "attended_sessions": 7,
        "attendance_rate": 0.875,
        "recent_sessions": [],
    }


@router.get("/sessions/")
@router.get("/sessions")
async def list_sessions(
    limit: int = 10,
    offset: int = 0,
    _user=Depends(INSTRUCTOR),
):
    items = [
        {
            "id": "ses-cs101-l4",
            "name": "CS101 Lecture 4",
            "status": "active",
        }
    ]
    return {"items": items, "total": len(items), "limit": limit, "offset": offset}


@router.post("/sessions/", status_code=201)
@router.post("/sessions", status_code=201)
async def create_session(body: SessionCreateBody, _user=Depends(INSTRUCTOR)):
    return {
        "id": str(uuid4()),
        "course_id": body.course_id,
        "name": body.name or body.title or "Untitled session",
        "session_type": body.session_type or "lecture",
        "scheduled_start": body.scheduled_start,
        "scheduled_end": body.scheduled_end,
        "status": "scheduled",
    }


@router.patch("/sessions/{session_id}")
async def update_session(session_id: str, body: SessionPatchBody, _user=Depends(INSTRUCTOR)):
    return {
        "id": session_id,
        "name": body.name or "Updated session",
        "status": body.status or "scheduled",
    }


@router.get("/checkins/")
@router.get("/checkins")
async def list_checkins(limit: int = 10, _user=Depends(STAFF)):
    return {"items": [], "total": 0, "limit": limit}


@router.get("/checkins/flagged")
async def flagged_checkins(_user=Depends(STAFF)):
    return {
        "items": [
            {
                "id": "chk-f1",
                "status": "flagged",
                "student_name": "Alex Chen",
                "risk_score": 0.62,
            }
        ],
        "total": 1,
    }


@router.get("/export/session/{session_id}")
async def export_session(
    session_id: str,
    format: Literal["csv", "json"] = Query("csv"),
    _user=Depends(INSTRUCTOR),
):
    records = [
        {
            "checkin_id": "chk-a1",
            "student_id": "stu-wei",
            "student_name": "Wei Tan",
            "student_email": "wei.tan@e.ntu.edu.sg",
            "session_id": session_id,
            "session_name": "CS101 Lecture 4",
            "status": "approved",
            "risk_score": 0.18,
        }
    ]
    summary = {"total_enrolled": 48, "attendance_rate": 0.85, "checked_in": 41}

    if format == "json":
        return {
            "session_id": session_id,
            "summary": summary,
            "records": records,
        }

    header = "student_id,student_name,student_email,session_date,session_name,status,checked_in_at,risk_score"
    csv = header + "\n" + "stu-wei,Wei Tan,wei.tan@e.ntu.edu.sg,2026-08-20,CS101 Lecture 4,approved,2026-08-20T09:02:11Z,0.18\n"
    return Response(
        content=csv,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="session-{session_id}.csv"'},
    )


@router.get("/enrollments/course/{course_id}")
async def course_enrollments(course_id: str, _user=Depends(INSTRUCTOR)):
    return {"course_id": course_id, "total_enrolled": 0, "students": []}


@router.get("/enrollments/my-enrollments")
async def my_enrollments(_user=Depends(require_roles("student", "ta", "instructor", "admin"))):
    return []
