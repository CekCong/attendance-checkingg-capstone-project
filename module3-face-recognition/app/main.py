from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.face import router as face_router
from app.api.liveness import router as liveness_router
from app.api.risk import router as risk_router
from app.api.health import router as health_router


app = FastAPI(
    title="SAIV Face Recognition Service",
    description="Face enrollment, verification, liveness detection, and risk scoring service",
    version="1.0.0"
)

# ---------------- CORS Middleware ----------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
        "version": "1.0.0",
        "endpoints": [
            "GET /health - Health check",
            "POST /face/enroll - Enroll a face for verification",
            "POST /face/verify - Verify a face against enrolled template",
            "POST /face/match - Legacy face matching (use /face/verify)",
            "POST /liveness/check - Perform liveness detection",
            "POST /risk/assess - Multi-signal risk assessment"
        ]
    }

#----------- Routers ------------------------
app.include_router(health_router)
app.include_router(face_router)
app.include_router(liveness_router)
app.include_router(risk_router)



