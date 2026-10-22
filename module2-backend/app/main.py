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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from contextlib import asynccontextmanager
from .routers import admin, audit, auth, checkins, courses, devices, enrollment, observability, rbac_stubs, sessions, users
from .database import engine, Base
from . import models

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: Initialize database schema ---
    Base.metadata.create_all(bind=engine)
    yield
    # --- Shutdown: Clean up resources if needed ---


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
app.include_router(observability.router, prefix="/api/v1")
app.include_router(rbac_stubs.router, prefix="/api/v1")




@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}
