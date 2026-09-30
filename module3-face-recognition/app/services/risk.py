"""
    Detect VPN/proxy usage.

    Check for:
    - Private IP ranges (10.x, 172.16-31.x, 192.168.x)
    - Localhost (127.x, ::1)
    - VPN keywords in user_agent
    - Known proxy headers (not available here, but could extend)

    Return (is_vpn: bool, confidence: float)
"""
import ipaddress

PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
)
VPN_KEYWORDS = (
    "vpn",
    "proxy",
    "tor",
    "anonymizer",
    "hidemyass",
    "nordvpn",
    "expressvpn",
)
LOOPBACK_CONFIDENCE = 1.0
PRIVATE_IP_CONFIDENCE = 0.7
PROXY_KEYWORD_CONFIDENCE = 0.8

def detect_vpn_proxy(ip_address: str, user_agent: str) -> tuple:
    is_suspicious_ip, ip_confidence = check_suspicious_ip(ip_address)
    is_proxy, proxy_confidence = check_proxy_usage(user_agent)

    is_vpn_or_proxy = is_suspicious_ip or is_proxy
    confidence = max(ip_confidence, proxy_confidence)

    return is_vpn_or_proxy, confidence


# Helper Functions

def check_suspicious_ip(ip_address: str) -> tuple:
    if not ip_address:
        return False, 0.5
    try:
        ip = ipaddress.ip_address(ip_address)

        # Localhost: 127.x.x.x or ::1
        if ip.is_loopback:
            return True, LOOPBACK_CONFIDENCE

        # Private IP
        if any(ip in network for network in PRIVATE_NETWORKS):
            return True, PRIVATE_IP_CONFIDENCE

        if not ip.is_global:
            return True, PRIVATE_IP_CONFIDENCE

    except ValueError:
        return True, 1.0

    return False, 0.0


def check_proxy_usage(user_agent: str) -> tuple:
    user_agent_lower = (user_agent or "").lower()

    if any(keyword in user_agent_lower for keyword in VPN_KEYWORDS):
        return True, PROXY_KEYWORD_CONFIDENCE

    return False, 0.0
