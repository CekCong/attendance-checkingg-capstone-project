"""Short-lived attendance invitations; enrollment and verification remain required."""
import os
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import qrcode
import qrcode.image.svg
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit import add_audit_log
from app.database import get_db
from app.models import EnrollmentModel, SessionModel
from app.rate_limit import check_rate_limit
from app.security import require_roles

router = APIRouter(tags=["Attendance invitations"])


def demo_mode():
    return os.getenv("ATTENDANCE_DEMO_MODE", "false").lower() == "true"


def student_origin(value):
    parts = urlsplit(value)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise HTTPException(422, "Enter the student website's HTTP or HTTPS address.")
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/"), "", ""))


def owned_session(db, session_id, user):
    lesson = db.get(SessionModel, session_id)
    if not lesson:
        raise HTTPException(404, "Lesson not found.")
    if user["role"] != "admin" and lesson.instructor_id != user["id"]:
        raise HTTPException(403, "Only the lesson's tutor can manage its attendance code.")
    return lesson


def invitation(lesson, website):
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    demo = demo_mode()
    active = (lesson.status == "active" and lesson.qr_code_secret and lesson.qr_code_expires_at
              and now < lesson.qr_code_expires_at and lesson.checkin_opens_at <= now < lesson.checkin_closes_at)
    if not active:
        if demo:
            reason = "expired" if lesson.qr_code_expires_at and now >= lesson.qr_code_expires_at else "not_open"
        elif lesson.status in {"closed", "cancelled"}:
            reason = lesson.status
        elif now >= lesson.scheduled_end:
            reason = "ended"
        elif now < lesson.scheduled_start - timedelta(minutes=15):
            reason = "upcoming"
        elif lesson.qr_code_expires_at and now >= lesson.qr_code_expires_at:
            reason = "expired"
        else:
            reason = "not_open"
        return {"open": False, "session_id": lesson.id, "reason": reason, "demo_mode": demo}
    url = student_origin(website) + "/#attendance=" + lesson.qr_code_secret
    image = qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage, border=4)
    return {"open": True, "session_id": lesson.id, "passcode": lesson.qr_code_secret, "demo_mode": demo,
            "expires_at": lesson.qr_code_expires_at.replace(tzinfo=timezone.utc),
            "join_url": url, "qr_svg": image.to_string(encoding="unicode")}


class OpenAttendance(BaseModel):
    student_url: str = Field(min_length=1, max_length=500)


@router.get("/sessions/{session_id}/attendance-code")
def get_code(session_id: str, response: Response, student_url: str = Query("http://localhost:3000", max_length=500),
             user=Depends(require_roles("instructor", "admin")), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return invitation(owned_session(db, session_id, user), student_origin(student_url))


@router.post("/sessions/{session_id}/attendance-code")
def open_attendance(session_id: str, payload: OpenAttendance, request: Request, response: Response,
                    user=Depends(require_roles("instructor", "admin")), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    website = student_origin(payload.student_url)
    lesson = owned_session(db, session_id, user)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    demo = demo_mode()
    if not demo and lesson.status not in {"scheduled", "active"}:
        raise HTTPException(400, "Attendance cannot be opened for a closed or cancelled lesson.")
    if not demo and (now < lesson.scheduled_start - timedelta(minutes=15) or now >= lesson.scheduled_end):
        raise HTTPException(400, "Open attendance from 15 minutes before the lesson until its end time.")
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    code = "".join(secrets.choice(alphabet) for _ in range(8))
    while db.query(SessionModel.id).filter(SessionModel.qr_code_secret == code).first():
        code = "".join(secrets.choice(alphabet) for _ in range(8))
    lesson.qr_code_secret = code
    lesson.qr_code_expires_at = now + timedelta(minutes=15) if demo else min(now + timedelta(minutes=15), lesson.scheduled_end)
    lesson.checkin_opens_at = now
    lesson.checkin_closes_at = lesson.qr_code_expires_at
    lesson.status = "active"
    if demo:
        lesson.actual_end = None
    if lesson.actual_start is None:
        lesson.actual_start = now
    add_audit_log(db, request, "session_updated", user_id=user["id"], resource_type="session",
                  resource_id=lesson.id, details="Attendance invitation opened or renewed" + (" (demo mode: schedule unrestricted)" if demo else ""))
    db.commit()
    db.refresh(lesson)
    return invitation(lesson, website)


class ResolveCode(BaseModel):
    code: str = Field(min_length=1, max_length=32)


@router.post("/attendance/resolve")
def resolve_code(payload: ResolveCode, response: Response,
                 user=Depends(require_roles("student")), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    allowed, _ = check_rate_limit(f"attendance_code:{user['id']}", limit=30, window=60)
    if not allowed:
        raise HTTPException(429, "Too many attempts. Wait a minute and try again.")
    code = payload.code.replace(" ", "").replace("-", "").upper()
    lesson = db.query(SessionModel).filter(SessionModel.qr_code_secret == code).first()
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    if (not lesson or lesson.status != "active" or not lesson.qr_code_expires_at
            or now >= lesson.qr_code_expires_at or not lesson.checkin_opens_at <= now < lesson.checkin_closes_at):
        raise HTTPException(400, "This attendance code is invalid, expired, or closed. Ask your tutor for the current code.")
    enrolled = db.query(EnrollmentModel).filter(EnrollmentModel.course_id == lesson.course_id,
        EnrollmentModel.student_id == user["id"], EnrollmentModel.is_active.is_(True)).first()
    if not enrolled:
        raise HTTPException(403, "You are not enrolled in this course. Ask your tutor to add you first.")
    return {"session_id": lesson.id, "class_code": lesson.course.code, "title": lesson.name,
            "qr_code": code, "expires_at": lesson.qr_code_expires_at.replace(tzinfo=timezone.utc)}
