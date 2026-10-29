"""Async client for Module 3's face-recognition and risk API."""

import os
from typing import Any, Dict, Optional

import httpx


FACE_SERVICE_URL = os.getenv(
    "FACE_SERVICE_URL", "http://localhost:8001"
).rstrip("/")


class FaceServiceError(Exception):
    """A safe, HTTP-shaped error returned by or while calling Module 3."""

    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


async def _post(path: str, payload: Dict[str, Any], timeout: float) -> Dict[str, Any]:
    try:
        # This is private service-to-service traffic, never an outbound proxy hop.
        async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
            response = await client.post(
                f"{FACE_SERVICE_URL}{path}",
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise FaceServiceError(503, "Face recognition service timed out") from exc
    except httpx.RequestError as exc:
        raise FaceServiceError(503, "Face recognition service unavailable") from exc

    if response.is_error:
        status_code = response.status_code if response.status_code < 500 else 503
        detail = "Face recognition service request failed"
        try:
            error_body = response.json()
            if isinstance(error_body, dict) and error_body.get("detail"):
                detail = str(error_body["detail"])
        except ValueError:
            pass
        raise FaceServiceError(status_code, detail)

    try:
        result = response.json()
    except ValueError as exc:
        raise FaceServiceError(
            503, "Face recognition service returned an invalid response"
        ) from exc

    if not isinstance(result, dict):
        raise FaceServiceError(
            503, "Face recognition service returned an invalid response"
        )
    return result


async def enroll_face(
    user_id: str,
    image: str,
    camera_consent: bool,
) -> Dict[str, Any]:
    return await _post(
        "/face/enroll",
        {
            "user_id": user_id,
            "image": image,
            "camera_consent": camera_consent,
        },
        timeout=10.0,
    )


async def check_liveness(
    image: str | list[str],
    challenge_type: str = "passive",
    reference_template_hash: Optional[str] = None,
    challenge_id: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "challenge_response": image,
        "challenge_type": challenge_type,
    }
    if reference_template_hash:
        payload["reference_template_hash"] = reference_template_hash
    if challenge_id:
        payload.update({
            "challenge_id": challenge_id,
            "user_id": user_id,
            "session_id": session_id,
        })
    return await _post("/liveness/check", payload, timeout=60.0)


async def create_liveness_challenge(user_id: str, session_id: str) -> Dict[str, Any]:
    return await _post(
        "/liveness/challenge",
        {"user_id": user_id, "session_id": session_id},
        timeout=5.0,
    )


async def verify_face(image: str, reference_template_hash: str) -> Dict[str, Any]:
    return await _post(
        "/face/verify",
        {
            "image": image,
            "reference_template_hash": reference_template_hash,
        },
        timeout=10.0,
    )


async def assess_risk(
    *,
    liveness_score: float,
    face_match_score: float,
    device_signature: Optional[str],
    device_public_key: Optional[str],
    device_challenge: Optional[str],
    ip_address: Optional[str],
    user_agent: Optional[str],
    latitude: float,
    longitude: float,
    accuracy: Optional[float],
) -> Dict[str, Any]:
    return await _post(
        "/risk/assess",
        {
            "liveness_score": liveness_score,
            "face_match_score": face_match_score,
            "device_signature": device_signature,
            "device_public_key": device_public_key,
            "device_challenge": device_challenge,
            "ip_address": ip_address,
            "user_agent": user_agent,
            "geolocation": {
                "latitude": latitude,
                "longitude": longitude,
                "accuracy": accuracy if accuracy is not None else 5000.0,
            },
        },
        timeout=5.0,
    )
