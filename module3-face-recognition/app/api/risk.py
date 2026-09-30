# =============================================================================
# RISK ASSESSMENT ENDPOINT (REQUIRED - 3 points in public tests)
# =============================================================================
from math import asin, cos, radians, sin, sqrt

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


def _clamp(value: float) -> float:
    return max(0.0, min(float(value), 1.0))


def _device_risk(signature: str | None, public_key: str | None) -> float:
    if signature is None and public_key is None:
        return MISSING_SIGNAL_RISK
    # Do not trust text that merely looks like a key. A valid attestation
    # protocol must verify a signature over a server-issued challenge.
    return 0.75


def _distance_meters(latitude, longitude, venue_latitude, venue_longitude) -> float:
    earth_radius_meters = 6_371_000
    latitude_delta = radians(venue_latitude - latitude)
    longitude_delta = radians(venue_longitude - longitude)
    start_latitude = radians(latitude)
    end_latitude = radians(venue_latitude)
    haversine = (
        sin(latitude_delta / 2) ** 2
        + cos(start_latitude) * cos(end_latitude) * sin(longitude_delta / 2) ** 2
    )
    return 2 * earth_radius_meters * asin(sqrt(haversine))


def _geolocation_risk(
    geolocation,
    venue_latitude,
    venue_longitude,
    allowed_radius_meters,
) -> float:
    if geolocation is None:
        return MISSING_SIGNAL_RISK
    if geolocation.accuracy < MIN_REASONABLE_ACCURACY_METERS:
        return 0.5

    if venue_latitude is None or venue_longitude is None:
        return MISSING_SIGNAL_RISK

    distance = _distance_meters(
        geolocation.latitude,
        geolocation.longitude,
        venue_latitude,
        venue_longitude,
    )
    if distance > allowed_radius_meters + geolocation.accuracy:
        return 1.0
    if distance > allowed_radius_meters or geolocation.accuracy > allowed_radius_meters:
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
    geolocation_risk = _geolocation_risk(
        request.geolocation,
        request.venue_latitude,
        request.venue_longitude,
        request.allowed_radius_meters,
    )

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

    required_signals_present = (
        request.liveness_score is not None
        and request.face_match_score is not None
        and request.ip_address is not None
        and request.geolocation is not None
    )

    return RiskAssessResponse(
        risk_score=risk_score,
        risk_level=_risk_level(risk_score),
        pass_threshold=required_signals_present and risk_score < RISK_THRESHOLD,
        risk_threshold=RISK_THRESHOLD,
        signal_breakdown=signal_breakdown,
        recommendations=recommendations,
    )
