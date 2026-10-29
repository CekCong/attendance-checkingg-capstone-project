# =============================================================================
# HEALTH ENDPOINTS
# =============================================================================
from fastapi import APIRouter

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {
        "status": "healthy",
        "service": "face-recognition",
    }


@router.get('/ready')
def readiness():
    from fastapi.responses import JSONResponse
    from app.services.liveness_challenge import redis_client
    try:
        redis_client().ping()
    except Exception:
        return JSONResponse(status_code=503, content={'status': 'unavailable'})
    # ArcFace was loaded by the startup lifespan before accepting requests.
    return {'status': 'ready'}
