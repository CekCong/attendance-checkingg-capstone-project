import ipaddress
import os
from math import  isfinite
import httpx
from base64 import b64decode
from binascii import Error
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

# Total risk score
def calculate_risk_score(request):
    """Return the weighted total and raw per-signal risk scores."""
    liveness_risk_score = liveness_risk(request.liveness_score)
    face_match_risk_score = face_match_risk(request.face_match_score)
    device_risk_score = device_risk(
        request.device_signature,
        request.device_public_key,
        request.device_challenge,
    )
    country_risk_score = ip_country_risk(request.ip_address)
    country_unknown = country_risk_score == 0.5
    network_risk_score = max(
        network_risk(request.ip_address, request.user_agent),
        country_risk_score,
    )

    if request.geolocation is None:
        geolocation_risk_score = 1.0
    else:
        geolocation_risk_score = geolocation_risk(
            request.geolocation.latitude,
            request.geolocation.longitude,
            request.geolocation.accuracy,
        )

    signal_breakdown = {
        "liveness": round(liveness_risk_score, 4),
        "face_match": round(face_match_risk_score, 4),
        "device": round(device_risk_score, 4),
        "network": round(network_risk_score, 4),
        "ip_country": round(country_risk_score, 4),
        "ip_country_unknown": float(country_unknown),
        "geolocation": round(geolocation_risk_score, 4),
    }
    risk_score = round(
        signal_breakdown["liveness"] * 0.25
        + signal_breakdown["face_match"] * 0.25
        + signal_breakdown["device"] * 0.20
        + signal_breakdown["network"] * 0.15
        + signal_breakdown["geolocation"] * 0.15,
        4,
    )
    return risk_score, signal_breakdown

# Liveness risk:
def liveness_risk(liveness_score):
    """Return the liveness risk score based on the liveness score."""
    if (
        isinstance(liveness_score, bool)
        or not isinstance(liveness_score, (int, float))
        or not isfinite(liveness_score)
        or not 0.0 <= liveness_score <= 1.0
):
        return 1.0
    return 1.0 - liveness_score

# Face match risk:
def face_match_risk(face_match_score):
    """Return the face match risk score based on the face match score."""
    if (
        isinstance(face_match_score, bool)
        or not isinstance(face_match_score, (int, float))
        or not isfinite(face_match_score)
        or not 0.0 <= face_match_score <= 1.0
    ):
        return 1.0
    return 1.0 - face_match_score

# Device attestation risk:
"""
    - Valid RSA-PSS/SHA-256 signature: 0.0
    - Missing, malformed, unsupported, or invalid credentials: 1.0
    - Wrong signature for the challenge: 1.0
"""
def device_risk(signature, public_key, challenge):
    """Verify an RSA-PSS/SHA-256 signature and return its device risk."""
    if not isinstance(signature, str) or not signature.strip():
        return 1.0
    if not isinstance(public_key, str) or not public_key.strip():
        return 1.0
    if not isinstance(challenge, str) or not challenge.strip():
        return 1.0

    try:
        decoded_signature = b64decode(signature.strip(), validate=True)
        parsed_public_key = serialization.load_pem_public_key(
            public_key.encode("utf-8")
        )
        if not isinstance(parsed_public_key, rsa.RSAPublicKey):
            return 1.0
        if parsed_public_key.key_size < 2048:
            return 1.0

        parsed_public_key.verify(
            decoded_signature,
            challenge.encode("utf-8"),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=32,
            ),
            hashes.SHA256(),
        )
    except (Error, InvalidSignature, UnsupportedAlgorithm, ValueError, TypeError):
        return 1.0

    return 0.0

# Network/VPN functions
"""
    - Invalid IP: 1.0
    - Private/local IP: 0.2 (Private IP ranges: 10.x.x.x, 172.16-31.x.x, 192.168.x.x)
    - VPN keyword in user agent: 0.3 (e.g., openvpn, wireguard, nordvpn, expressvpn, surfshark, protonvpn)
    - Datacenter IP: 0.4
    - VPN IP: 0.6
    - Proxy IP: 0.7
    - Tor exit node: 1.0

    Risk score = highest detected risk
"""
VPN_KEYWORDS = ("openvpn","wireguard","nordvpn","expressvpn","surfshark","protonvpn")

INVALID_IP_RISK = 1.0
PRIVATE_IP_RISK = 0.2
VPN_KEYWORD_RISK = 0.3
DATACENTER_IP_RISK = 0.4
VPN_IP_RISK = 0.6
PROXY_IP_RISK = 0.7
TOR_IP_RISK = 1.0

IPINFO_TOKEN = os.getenv("IPINFO_TOKEN")


def get_ip_info(ip_address):
    """Return IPInfo data when an API token is configured."""
    if not IPINFO_TOKEN:
        return {}

    try:
        response = httpx.get(
            f"https://ipinfo.io/{ip_address}/json",
            params={"token": IPINFO_TOKEN},
            timeout=5.0,
        )
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}
    except (httpx.HTTPError, ValueError):
        return {}


def is_datacenter_ip(ip_address):
    data = get_ip_info(ip_address)
    return data.get("company", {}).get("type") == "hosting"


def is_vpn_ip(ip_address):
    data = get_ip_info(ip_address)
    return bool(data.get("privacy", {}).get("vpn", False))


def is_proxy_ip(ip_address):
    data = get_ip_info(ip_address)
    return bool(data.get("privacy", {}).get("proxy", False))


def is_tor_exit_node(ip_address):
    data = get_ip_info(ip_address)
    return bool(data.get("privacy", {}).get("tor", False))


def ip_country_risk(ip_address):
    """Return high risk for a public IP geolocated outside Singapore."""
    try:
        ip = ipaddress.ip_address(ip_address)
    except (ValueError, TypeError):
        return 0.5

    if ip.is_private or ip.is_loopback:
        return 0.0

    ip_info = get_ip_info(str(ip))
    country = ip_info.get("country")
    if not isinstance(country, str) or len(country) != 2:
        return 0.5
    return 1.0 if country.upper() != "SG" else 0.0


def network_risk(ip_address, user_agent):
    """Return the highest detected network risk score."""
    try:
        ip = ipaddress.ip_address(ip_address)
    except (ValueError, TypeError):
        return INVALID_IP_RISK

    ip_address_text = str(ip)
    if ip.is_private or ip.is_loopback:
        return max(PRIVATE_IP_RISK, VPN_KEYWORD_RISK if any(
            keyword in (user_agent or "").lower() for keyword in VPN_KEYWORDS
        ) else 0.0)
    info = get_ip_info(ip_address_text)
    if not info:
        return 1.0

    risk = 0.0

    if ip.is_private or ip.is_loopback:
        risk = max(risk, PRIVATE_IP_RISK)

    user_agent_lower = (user_agent or "").lower()
    if any(keyword in user_agent_lower for keyword in VPN_KEYWORDS):
        risk = max(risk, VPN_KEYWORD_RISK)

    privacy = info.get("privacy") or {}
    company = info.get("company") or {}
    if not isinstance(privacy, dict) or not isinstance(company, dict):
        return 1.0
    if company.get("type") == "hosting":
        risk = max(risk, DATACENTER_IP_RISK)
    if privacy.get("vpn"):
        risk = max(risk, VPN_IP_RISK)
    if privacy.get("proxy"):
        risk = max(risk, PROXY_IP_RISK)
    if privacy.get("tor"):
        risk = max(risk, TOR_IP_RISK)

    return risk

# Geolocation functions
""" -Invalid coordinates/accuracy --> risk = 1.0
    -accuracy < 0 --> risk = 1.0
    -accuracy 0-10m --> risk = 0.7 
    -accuracy 10-50m --> risk = 0.0
    -accuracy 50-100m --> risk = 0.2
    -accuracy 100-500m --> risk = 0.4
    -accuracy 500m-5000m --> risk = 0.7
    -accuracy > 5000m --> risk = 1.0
"""
def geolocation_risk(latitude, longitude, accuracy):
    """Return GPS risk from coordinate validity and reported accuracy."""
    try:
        values_are_finite = all(
            isfinite(value) for value in (latitude, longitude, accuracy)
        )
    except (TypeError, ValueError):
        return 1.0
    if not values_are_finite:
        return 1.0
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        return 1.0
    if accuracy < 0:
        return 1.0
    if accuracy <= 10:
        return 0.7
    if accuracy <= 50:
        return 0.0
    if accuracy <= 100:
        return 0.2
    if accuracy <= 500:
        return 0.4
    if accuracy <= 5_000:
        return 0.7
    return 1.0


