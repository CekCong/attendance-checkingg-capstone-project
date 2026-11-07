"""Student-facing explanations derived from recorded verification results."""
import json


def liveness_failure_code(details):
    """Keep a bounded reason code, never model diagnostics or biometric data."""
    if not isinstance(details, dict):
        return None
    error = details.get("error")
    if error == "Identical frames cannot satisfy an active challenge.":
        return "liveness_no_motion"
    if error in {
        "Every frame must contain exactly one face.",
        "Every frame must contain visible face landmarks.",
        "A face embedding could not be extracted from every frame.",
    }:
        return "liveness_face_unclear"
    if error == "Faces do not match across all frames.":
        return "liveness_face_inconsistent"
    if error == "Not every frame matches the enrolled face.":
        return "liveness_reference_mismatch"
    if not error and details.get("action_detected") is False:
        return "liveness_action_failed"
    return None


def rejection_reasons(status, factors, challenge_type=None, reviewed_at=None, review_notes=None):
    if status != "rejected":
        return []
    if reviewed_at:
        return [f"Your instructor rejected this check-in: {review_notes}" if review_notes
                else "Your instructor rejected this check-in. Contact them for clarification before retrying."]
    factors = json.loads(factors) if isinstance(factors, str) else factors or []
    types = {factor["type"] for factor in factors}
    reasons = []
    liveness_messages = {
        "liveness_no_motion": "The camera frames did not show movement. Use a live camera and follow the challenge prompts.",
        "liveness_face_unclear": "Your face could not be read clearly throughout the challenge. Keep one face fully visible with good lighting.",
        "liveness_face_inconsistent": "Your face could not be tracked consistently throughout the challenge. Keep only yourself in view and follow the prompts.",
        "liveness_reference_mismatch": "The face captured during the challenge did not consistently match your enrolled face. Use your own account and contact your instructor if this continues.",
        "liveness_action_failed": {
            "smile": "The smile sequence was not detected reliably. Start neutral, smile when prompted, then return to neutral.",
            "blink": "The blink sequence was not detected reliably. Start with eyes open, close and open them when prompted, then look straight ahead.",
            "head_turn": "The head-turn sequence was not detected reliably. Look straight ahead, turn when prompted, then face forward again.",
        }.get(challenge_type, "The requested movement was not detected reliably. Follow each on-screen challenge prompt."),
    }
    specific = [message for code, message in liveness_messages.items() if code in types]
    reasons.extend(specific)
    if "liveness_failed" in types and not specific:
        reasons.append("The liveness check did not pass. Keep your face visible and follow each prompt. A more detailed reason was not recorded.")
    if "face_match_failed" in types:
        reasons.append("Your captured face did not match the enrolled face. Use your own account and contact your instructor if this continues.")
    if "critical_geofence_exceeded" in types:
        reasons.append("Your reported location was too far from the lesson venue. Retry from the classroom with location access enabled.")
    if any(factor["type"] == "ip_country_risk" and factor.get("weight", 0) >= 1 for factor in factors):
        reasons.append("Your network connection was detected outside Singapore. Check your network or VPN and retry from Singapore.")
    return reasons or ["This check-in was rejected, but no detailed reason was recorded. Contact your instructor for help."]
