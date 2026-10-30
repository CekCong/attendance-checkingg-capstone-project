"""Create finite weekly lesson schedules atomically, in Singapore time."""
import hashlib
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session

from app.audit import add_audit_log
from app.course_access import require_course_staff_access
from app.database import get_db
from app.models import CourseModel, SessionModel, SessionSeriesModel, SessionOccurrenceModel, UserModel
from app.security import require_roles

router = APIRouter(prefix="/sessions", tags=["Session Management"])


class RecurringSessionCreate(BaseModel):
    request_id: uuid.UUID
    course_id: str
    name: str = Field(min_length=1, max_length=255)
    session_type: Literal["lecture", "tutorial", "lab", "exam"] = "tutorial"
    start_date: date
    end_date: date
    weekday: int = Field(ge=0, le=6)  # Monday = 0
    start_time: time
    end_time: time
    timezone: Literal["Asia/Singapore"] = "Asia/Singapore"
    venue_name: str | None = Field(default=None, max_length=255)

    @field_validator("name", mode="before")
    @classmethod
    def trim_name(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def validate_range(self):
        if self.end_date < self.start_date:
            raise ValueError("End date must be on or after start date.")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("Schedule at most one year at a time.")
        if self.start_time.tzinfo or self.end_time.tzinfo:
            raise ValueError("Enter local times without a UTC offset.")
        if self.end_time <= self.start_time:
            raise ValueError("Lesson end time must be after its start time on the same day.")
        return self

    def occurrences(self):
        day = self.start_date + timedelta(days=(self.weekday - self.start_date.weekday()) % 7)
        tz = ZoneInfo(self.timezone)
        result = []
        while day <= self.end_date:
            start = datetime.combine(day, self.start_time, tz).astimezone(timezone.utc)
            end = datetime.combine(day, self.end_time, tz).astimezone(timezone.utc)
            result.append((start, end))
            day += timedelta(days=7)
        return result


def series_response(db, series_id):
    rows = (db.query(SessionModel).join(SessionOccurrenceModel, SessionOccurrenceModel.session_id == SessionModel.id)
            .filter(SessionOccurrenceModel.series_id == series_id).order_by(SessionModel.scheduled_start).all())
    return {"series_id": series_id, "count": len(rows), "sessions": [
        {"id": row.id, "course_id": row.course_id, "scheduled_start": row.scheduled_start,
         "scheduled_end": row.scheduled_end} for row in rows
    ]}


@router.post("/recurring", status_code=201)
def create_recurring_sessions(payload: RecurringSessionCreate, request: Request,
                              user=Depends(require_roles("instructor", "admin")), db: Session = Depends(get_db)):
    course = db.get(CourseModel, payload.course_id)
    if not course or not course.is_active:
        raise HTTPException(404, "Active course not found.")
    require_course_staff_access(db, user, course.id)
    # Serialize schedules for the same tutor, including retries from another tab.
    db.query(UserModel).filter(UserModel.id == user["id"]).with_for_update().one()
    series_id = str(payload.request_id)
    schedule = payload.model_dump_json(exclude={"request_id"})
    fingerprint = hashlib.sha256(schedule.encode()).hexdigest()
    existing = db.get(SessionSeriesModel, series_id)
    if existing:
        if existing.instructor_id != user["id"] or existing.payload_hash != fingerprint:
            raise HTTPException(409, "This request was already used for a different schedule.")
        return series_response(db, series_id)

    occurrences = payload.occurrences()
    if not occurrences:
        raise HTTPException(422, "There are no lessons on that weekday within the selected dates.")
    if occurrences[0][0] <= datetime.now(timezone.utc):
        raise HTTPException(422, "The first lesson must be in the future. Choose a later start date or time.")

    # Database timestamps are UTC without an offset; convert explicitly before storage/comparison.
    utc_pairs = [(start.replace(tzinfo=None), end.replace(tzinfo=None)) for start, end in occurrences]
    existing_lessons = db.query(SessionModel).filter(
        SessionModel.instructor_id == user["id"],
        SessionModel.status.in_(["scheduled", "active"]),
        SessionModel.scheduled_start < utc_pairs[-1][1],
        SessionModel.scheduled_end > utc_pairs[0][0],
    ).all()
    for start, end in utc_pairs:
        if any(lesson.scheduled_start < end and lesson.scheduled_end > start for lesson in existing_lessons):
            local = start.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(payload.timezone))
            raise HTTPException(409, f"Timetable conflict on {local:%d %b %Y at %H:%M}. No lessons were added.")

    db.add(SessionSeriesModel(id=series_id, instructor_id=user["id"], course_id=course.id,
                              payload_hash=fingerprint, schedule=schedule))
    db.flush()
    for start, end in utc_pairs:
        lesson = SessionModel(
            id=str(uuid.uuid4()), course_id=course.id, instructor_id=user["id"], name=payload.name,
            session_type=payload.session_type, status="scheduled", scheduled_start=start, scheduled_end=end,
            checkin_opens_at=start - timedelta(minutes=15), checkin_closes_at=min(start + timedelta(minutes=30), end),
            venue_name=payload.venue_name or course.venue_name, venue_latitude=course.venue_latitude,
            venue_longitude=course.venue_longitude, geofence_radius_meters=course.geofence_radius_meters,
            risk_threshold=course.risk_threshold, require_face_match=course.require_face_recognition,
        )
        db.add(lesson)
        db.flush()
        db.add(SessionOccurrenceModel(session_id=lesson.id, series_id=series_id))
        add_audit_log(db, request, "session_created", user_id=user["id"], resource_type="session",
                      resource_id=lesson.id, details=f"course_id={course.id};series_id={series_id}")
    db.commit()
    return series_response(db, series_id)
