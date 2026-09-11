# =============================================================================
# RISK ASSESSMENT ENDPOINT (REQUIRED - 3 points in public tests)
# =============================================================================
from fastapi import APIRouter
from app.schemas.risk import RiskAssessRequest, RiskAssessResponse
from app.services.risk import detect_vpn_proxy

router = APIRouter(tags=["Risk"])

LIVENESS_WEIGHT = 0.25
FACE_MATCH_WEIGHT = 0.25
DEVICE_WEIGHT = 0.20
NETWORK_WEIGHT = 0.15
GEOLOCATION_WEIGHT = 0.15
MISSING_SIGNAL_RISK = 0.50
RISK_THRESHOLD = 0.50
MEDIUM_RISK_THRESHOLD = 0.30
HIGH_RISK_THRESHOLD = 0.50
CRITICAL_RISK_THRESHOLD = 0.70
MIN_REASONABLE_ACCURACY_METERS = 5.0
MAX_REASONABLE_ACCURACY_METERS = 5000.0


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _device_risk(signature: str | None, public_key: str | None) -> float:
    if signature is None and public_key is None:
        return MISSING_SIGNAL_RISK
    if signature and public_key and "PUBLIC KEY" in public_key:
        return 0.0
    return 0.75


def _geolocation_risk(geolocation) -> float:
    if geolocation is None:
        return MISSING_SIGNAL_RISK
    if not (-90 <= geolocation.latitude <= 90 and -180 <= geolocation.longitude <= 180):
        return 1.0
    if geolocation.accuracy < 0 or geolocation.accuracy > MAX_REASONABLE_ACCURACY_METERS:
        return 1.0
    if geolocation.accuracy < MIN_REASONABLE_ACCURACY_METERS:
        return 0.5
    return 0.0


def _risk_level(risk_score: float) -> str:
    if risk_score >= CRITICAL_RISK_THRESHOLD:
        return "CRITICAL"
    if risk_score >= HIGH_RISK_THRESHOLD:
        return "HIGH"
    if risk_score >= MEDIUM_RISK_THRESHOLD:
        return "MEDIUM"
    return "LOW"

@router.post("/risk/assess", response_model=RiskAssessResponse)
async def assess_risk(request: RiskAssessRequest):
    """
    Perform multi-signal risk assessment.

    TODO: Implement the following:
    1. Collect all available signals from request
    2. Calculate individual signal scores (0.0 = safe, 1.0 = risky)
    3. Apply weighted fusion:
       - Liveness: 25%
       - Face match: 25%
       - Device attestation: 20%
       - Network/VPN: 15%
       - Geolocation: 15%
    4. Calculate combined risk_score
    5. Determine risk_level:
       - LOW: risk_score < 0.3
       - MEDIUM: 0.3 <= risk_score < 0.5
       - HIGH: 0.5 <= risk_score < 0.7
       - CRITICAL: risk_score >= 0.7
    6. pass_threshold = (risk_score < 0.50)
    7. Generate recommendations for low-scoring signals

    Signal Analysis:
    - Liveness: Invert score (low liveness = high risk)
    - Face match: Invert score (low match = high risk)
    - Device: Check signature validity, public key format
    - Network: Detect VPN/proxy (private IPs, Tor exit nodes)
    - Geolocation: Check accuracy, validate coordinates

    VPN/Proxy Detection Hints:
    - Private IP ranges: 10.x.x.x, 172.16-31.x.x, 192.168.x.x
    - Check user_agent for VPN indicators
    - High geolocation accuracy (< 10m) might be spoofed
    - Very low accuracy (> 5000m) indicates issues
    """
    liveness_risk = (
        1.0 - _clamp(request.liveness_score)
        if request.liveness_score is not None
        else MISSING_SIGNAL_RISK
    )
    face_match_risk = (
        1.0 - _clamp(request.face_match_score)
        if request.face_match_score is not None
        else MISSING_SIGNAL_RISK
    )
    device_risk = _device_risk(request.device_signature, request.device_public_key)
    _, network_risk = detect_vpn_proxy(request.ip_address, request.user_agent)
    geolocation_risk = _geolocation_risk(request.geolocation)

    signal_breakdown = {
        "liveness": liveness_risk * LIVENESS_WEIGHT,
        "face_match": face_match_risk * FACE_MATCH_WEIGHT,
        "device": device_risk * DEVICE_WEIGHT,
        "network": network_risk * NETWORK_WEIGHT,
        "geolocation": geolocation_risk * GEOLOCATION_WEIGHT,
    }
    signal_breakdown = {name: round(value, 4) for name, value in signal_breakdown.items()}
    risk_score = round(sum(signal_breakdown.values()), 4)

    recommendations = []
    if liveness_risk >= 0.5:
        recommendations.append("Improve lighting and face visibility")
    if face_match_risk >= 0.5:
        recommendations.append("Re-enroll face or improve image quality")
    if network_risk >= 0.5:
        recommendations.append("Disable VPN for check-in")
    if geolocation_risk >= 0.5:
        recommendations.append("Enable precise location services")

    return RiskAssessResponse(
        risk_score=risk_score,
        risk_level=_risk_level(risk_score),
        pass_threshold=risk_score < RISK_THRESHOLD,
        risk_threshold=RISK_THRESHOLD,
        signal_breakdown=signal_breakdown,
        recommendations=recommendations,
    )
