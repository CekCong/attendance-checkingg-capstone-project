# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

from typing import Any, Dict

from pydantic import BaseModel

class LivenessRequest(BaseModel):
    """Request model for liveness check."""
    challenge_response: str  # Base64 encoded image
    challenge_type: str = "passive"  # passive, blink, head_turn


class LivenessResponse(BaseModel):
    """Response model for liveness check."""
    liveness_passed: bool
    liveness_score: float  # 0.0 to 1.0
    liveness_threshold: float  # Default: 0.60
    face_embedding_hash: str
    details: Dict[str, Any]
