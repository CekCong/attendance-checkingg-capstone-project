"""
SAIV Backend API - Module 2

Endpoints from docs/API-SPECIFICATION.md (base: /api/v1):

Authentication
- POST /auth/register
- POST /auth/login
- POST /auth/refresh

Users
- GET /users/me
- PUT /users/me
- GET /users/
- GET /users/{user_id}
- PATCH /users/{user_id}
- POST /users/me/face/enroll

Courses
- GET /courses/
- GET /courses/{course_id}
- POST /courses/
- PUT /courses/{course_id}
- DELETE /courses/{course_id}

Sessions
- GET /sessions/
- GET /sessions/active
- GET /sessions/my-sessions
- GET /sessions/{session_id}
- POST /sessions/
- PATCH /sessions/{session_id}
- DELETE /sessions/{session_id}

Check-ins
- POST /checkins/
- GET /checkins/
- GET /checkins/my-checkins
- GET /checkins/session/{session_id}
- GET /checkins/flagged
- GET /checkins/{checkin_id}
- POST /checkins/{id}/appeal
- POST /checkins/{id}/review

Statistics
- GET /stats/overview
- GET /stats/sessions/{session_id}
- GET /stats/courses/{course_id}
- GET /stats/students/{student_id}

Devices
- POST /devices/register
- GET /devices/my-devices
- DELETE /devices/{device_id}
- PATCH /devices/{device_id}

Enrollments
- GET /enrollments/my-enrollments
- GET /enrollments/course/{course_id}
- POST /enrollments/
- POST /enrollments/bulk
- DELETE /enrollments/{enrollment_id}

Audit Logs
- GET /audit/

Export
- GET /export/attendance/{course_id}
- GET /export/session/{session_id}

Admin (required for automated testing)
- PATCH /admin/users/{user_id}/deactivate
- PATCH /admin/users/{user_id}/activate
- POST /admin/users/bulk
- PATCH /admin/sessions/{session_id}/status
- POST /admin/enrollments/

Health
- GET /health
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .routers import admin, audit, auth, checkins, courses, devices, enrollment, export, rbac_stubs, sessions, stats, users
from .database import engine, Base, SessionLocal
from . import models
from .retention import cleanup_expired_checkins

logger = logging.getLogger(__name__)


def _ensure_audit_action_values() -> None:
    if engine.dialect.name != "postgresql":
        return
    with engine.begin() as connection:
        for action in models.AUDIT_ACTION_VALUES:
            connection.execute(text(
                f"ALTER TYPE audit_action_enum ADD VALUE IF NOT EXISTS '{action}'"
            ))


async def _retention_cleanup_worker() -> None:
    interval = max(int(os.getenv("RETENTION_CLEANUP_INTERVAL_SECONDS", "3600")), 60)
    while True:
        db = SessionLocal()
        try:
            cleanup_expired_checkins(db)
        except Exception:
            db.rollback()
            logger.exception("Check-in retention cleanup failed")
        finally:
            db.close()
        await asyncio.sleep(interval)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: Initialize database schema ---
    Base.metadata.create_all(bind=engine)
    _ensure_audit_action_values()
    cleanup_task = asyncio.create_task(_retention_cleanup_worker())
    try:
        yield
    finally:
        cleanup_task.cancel()
        with suppress(asyncio.CancelledError):
            await cleanup_task


app = FastAPI(
    lifespan=lifespan,
    title="SAIV Backend API",
    description="Secure Attendance & Identity Verification System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(courses.router, prefix="/api/v1")
app.include_router(sessions.router, prefix="/api/v1")
app.include_router(devices.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(enrollment.router, prefix="/api/v1")
app.include_router(checkins.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(audit.router, prefix="/api/v1")
app.include_router(stats.router, prefix="/api/v1")
app.include_router(export.router, prefix="/api/v1")
app.include_router(rbac_stubs.router, prefix="/api/v1")




@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}
