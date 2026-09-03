# =============================================================================
# HEALTH ENDPOINTS
# =============================================================================
from fastapi import APIRouter

router = APIRouter(tags=["Health"])

@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status" : "healthy",
            "service" : "face-recognition"
            }