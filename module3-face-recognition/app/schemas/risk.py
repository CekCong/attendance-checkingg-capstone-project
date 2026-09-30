# =============================================================================
# REQUEST/RESPONSE MODELS
# =============================================================================

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, IPvAnyAddress

class GeolocationData(BaseModel):
    """Geolocation data for risk assessment."""
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float = Field(ge=0, le=5000)


class RiskAssessRequest(BaseModel):
    """Request model for risk assessment."""
    liveness_score: Optional[float] = Field(default=None, ge=0, le=1)
    face_match_score: Optional[float] = Field(default=None, ge=0, le=1)
    device_signature: Optional[str] = None
    device_public_key: Optional[str] = None
    ip_address: Optional[IPvAnyAddress] = None
    user_agent: Optional[str] = None
    geolocation: Optional[GeolocationData] = None
    venue_latitude: Optional[float] = Field(default=None, ge=-90, le=90)
    venue_longitude: Optional[float] = Field(default=None, ge=-180, le=180)
    allowed_radius_meters: float = Field(default=100.0, gt=0, le=10000)


class RiskAssessResponse(BaseModel):
    """Response model for risk assessment."""
    risk_score: float  # 0.0 to 1.0
    risk_level: str  # LOW, MEDIUM, HIGH, CRITICAL
    pass_threshold: bool
    risk_threshold: float  # Default: 0.50
    signal_breakdown: Dict[str, float]
    recommendations: List[str]
