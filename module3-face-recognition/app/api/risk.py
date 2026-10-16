# =============================================================================
# RISK ASSESSMENT ENDPOINT (REQUIRED - 3 points in public tests)
# =============================================================================
from fastapi import APIRouter
from app.schemas.risk import RiskAssessRequest, RiskAssessResponse
from app.services.risk import calculate_risk_score

router = APIRouter(tags=["Risk"])

RISK_THRESHOLD = 0.50
MEDIUM_RISK_THRESHOLD = 0.30
HIGH_RISK_THRESHOLD = 0.50
CRITICAL_RISK_THRESHOLD = 0.70


def risk_level(risk_score: float) -> str:
    if risk_score >= CRITICAL_RISK_THRESHOLD:
        return "CRITICAL"
    if risk_score >= HIGH_RISK_THRESHOLD:
        return "HIGH"
    if risk_score >= MEDIUM_RISK_THRESHOLD:
        return "MEDIUM"
    return "LOW"

@router.post("/risk/assess", response_model=RiskAssessResponse)
async def assess_risk(request: RiskAssessRequest):
    risk_score, signal_breakdown = calculate_risk_score(request)

    recommendations = []
    if signal_breakdown["liveness"] >= 0.5:
        recommendations.append("Improve lighting and face visibility")
    if signal_breakdown["face_match"] >= 0.5:
        recommendations.append("Re-enroll face or improve image quality")
    if signal_breakdown["device"] >= 0.5:
        recommendations.append("Complete device attestation")
    if signal_breakdown["network"] >= 0.5:
        recommendations.append("Disable VPN for check-in")
    if signal_breakdown["geolocation"] >= 0.5:
        recommendations.append("Enable precise location services")

    return RiskAssessResponse(
        risk_score=risk_score,
        risk_level=risk_level(risk_score),
        pass_threshold=risk_score < RISK_THRESHOLD,
        risk_threshold=RISK_THRESHOLD,
        signal_breakdown=signal_breakdown,
        recommendations=recommendations,
    )
