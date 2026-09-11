import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.face import router as face_router
from app.api.liveness import router as liveness_router
from app.api.risk import router as risk_router
from app.api.health import router as health_router

SERVICE_TITLE = "SAIV Face Recognition Service"
SERVICE_DESCRIPTION = "Face enrollment, verification, liveness detection, and risk scoring service"
SERVICE_VERSION = "1.0.0"
DEFAULT_CORS_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"

app = FastAPI(
    title=SERVICE_TITLE,
    description=SERVICE_DESCRIPTION,
    version=SERVICE_VERSION,
)

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
