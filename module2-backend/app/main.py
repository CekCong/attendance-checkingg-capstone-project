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
- POST /devices/challenge
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

import time

from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Histogram,
    generate_latest,
)
import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from .routers import (
    admin,
    audit,
    auth,
    checkins,
    courses,
    devices,
    enrollment,
    export,
    sessions,
    stats,
    users,
)
from .database import SessionLocal, engine
from .rate_limit import get_redis_client
from .admission import DatabaseAdmissionMiddleware
from .runtime_security import validate_runtime_security
from .security import SECRET_KEY
from .retention import cleanup_expired_checkins, cleanup_expired_users
from .migrate import check_runtime_database

logger = logging.getLogger(__name__)


async def _retention_cleanup_worker() -> None:
    interval = max(int(os.getenv("RETENTION_CLEANUP_INTERVAL_SECONDS", "3600")), 60)
    while True:
        db = SessionLocal()
        try:
            cleanup_expired_checkins(db)
            cleanup_expired_users(db)
        except Exception:
            db.rollback()
            logger.exception("Personal-data retention cleanup failed")
        finally:
            db.close()
        await asyncio.sleep(interval)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Validate runtime configuration and database permissions before serving requests.
    validate_runtime_security(signing_key=SECRET_KEY)
    check_runtime_database()
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

HTTP_REQUESTS = Counter(
    "saiv_http_requests_total",
    "Total number of HTTP requests",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION = Histogram(
    "saiv_http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)

@app.middleware("http")
async def prometheus_metrics(request: Request, call_next):
    if request.url.path == "/metrics":
        return await call_next(request)

    start = time.perf_counter()
    method = request.method if request.method in {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"} else "OTHER"
    status = "500"

    try:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        status = str(response.status_code)
        return response
    finally:
        duration = time.perf_counter() - start

        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")

        HTTP_REQUESTS.labels(
            method=method,
            path=path,
            status=status,
        ).inc()

        HTTP_REQUEST_DURATION.labels(
            method=method,
            path=path,
        ).observe(duration)

@app.get("/metrics", include_in_schema=False)
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS", "http://localhost:3000,http://localhost:8501"
    ).split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(DatabaseAdmissionMiddleware)

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




@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}


@app.get("/ready")
def readiness(response: Response):
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        client = get_redis_client()
        if client is None or not client.ping():
            raise RuntimeError("Redis unavailable")
    except Exception:
        response.status_code = 503
        return {"status": "unavailable"}
    return {"status": "ready"}
