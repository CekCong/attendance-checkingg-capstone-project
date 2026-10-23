"""Instructor observability stubs: stats, check-in queues, and exports."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import SessionModel
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


@router.get("/enrollments/course/{course_id}")
async def course_enrollments(course_id: str, _user=Depends(INSTRUCTOR)):
    return {"course_id": course_id, "total_enrolled": 0, "students": []}


@router.get("/enrollments/my-enrollments")
async def my_enrollments(_user=Depends(require_roles("student", "ta", "instructor", "admin"))):
    return []
