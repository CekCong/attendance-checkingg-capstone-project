# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

from typing import Any, Dict, Literal
from pydantic import BaseModel


class LivenessChallengeRequest(BaseModel):
    """Request a challenge bound to one user and attendance session."""
    user_id: str
    session_id: str


class LivenessChallengeResponse(BaseModel):
    """Short-lived challenge returned to Module 2."""
    challenge_id: str
    challenge_type: Literal["blink", "head_turn", "smile"]
    expires_in: int

class LivenessRequest(BaseModel):
    """Request model for liveness check."""
    challenge_response: str | list[str] # Base64 encoded image / image frames
    challenge_type: str = "passive"  # passive, blink, head_turn, smile
    reference_template_hash: str | None = None
    challenge_id: str | None = None
    user_id: str | None = None
    session_id: str | None = None


class LivenessResponse(BaseModel):
    """Response model for liveness check."""
    liveness_passed: bool
    liveness_score: float  # 0.0 to 1.0
    liveness_threshold: float  # Default: 0.60
    face_embedding_hash: str
    details: Dict[str, Any]
