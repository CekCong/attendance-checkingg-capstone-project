import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.api.face import router as face_router
from app.api.liveness import router as liveness_router
from app.api.risk import router as risk_router
from app.api.health import router as health_router
from app.services.arc_face import get_arcface_model

SERVICE_TITLE = "SAIV Face Recognition Service"
SERVICE_DESCRIPTION = "Face enrollment, verification, liveness detection, and risk scoring service"
SERVICE_VERSION = "1.0.0"
DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load ArcFace before reporting the service as ready."""
    get_arcface_model()
    yield

app = FastAPI(
    title=SERVICE_TITLE,
    description=SERVICE_DESCRIPTION,
    version=SERVICE_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def sanitized_validation_error_handler(request, exc):
    """Return validation errors without echoing submitted biometric data."""
    safe_errors = [
        {
            "type": error.get("type", "validation_error"),
            "loc": list(error.get("loc", ())),
            "msg": "Invalid request value.",
        }
        for error in exc.errors()
    ]
    return JSONResponse(status_code=422, content={"detail": safe_errors})

# ---------------- CORS Middleware ----------------
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        DEFAULT_CORS_ORIGINS,
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


#----------- Root Endpoint --------------
@app.get("/")
async def root():
    """List available endpoints."""
    return {
        "service": "SAIV Face Recognition & Risk Service",
        "version": SERVICE_VERSION,
        "endpoints": [
            "/health",
            "/face/enroll",
            "/face/verify",
            "/face/match",
            "/liveness/check",
            "/risk/assess",
        ]
    }

#----------- Routers ------------------------
app.include_router(health_router)
app.include_router(face_router)
app.include_router(liveness_router)
app.include_router(risk_router)
