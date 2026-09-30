# =============================================================================
# LIVENESS DETECTION ENDPOINT (REQUIRED - partial; BONUS for advanced)
# =============================================================================
"""
    Perform liveness detection on submitted image.
    Take in a base64 encoded image, and challenge type (blink, head_turn, passive), returns face embedding hash and liveness score.


    TODO: Implement the following:
    1. Decode base64 image to numpy array
    2. Detect face using MediaPipe FaceDetection
    3. If no face detected, return with liveness_passed=False
    4. Analyze face for liveness signals:

    REQUIRED (for partial credit):
    - Basic face detection confidence
    - Image quality assessment
    - Face size validation

    BONUS (for extra credit - see API-SPECIFICATION.md):
    - MediaPipe Face Mesh 3D analysis (468 landmarks)
    - Depth cue analysis (nose_tip_z coordinate)
    - Face mesh completeness check
    - Challenge-response detection (blink, head movement)

    Challenge Types:
    - "passive": No user action required (depth/texture analysis)
    - "blink": Detect eye blink (compare eye aspect ratios)
    - "head_turn": Detect head rotation (face mesh landmarks)

    5. Calculate liveness_score (0.0 to 1.0)
    6. liveness_passed = (liveness_score >= 0.60)
    7. Generate face embedding hash

    Depth Analysis Hints (BONUS):
    - Use MediaPipe FaceMesh to get 3D landmarks
    - nose_tip_z (landmark 1, z-coordinate) indicates depth
    - Real faces: |nose_tip_z| > 0.03 (significant depth)
    - Flat images: |nose_tip_z| < 0.01 (minimal depth)
    """


from fastapi import APIRouter, HTTPException
from app.schemas.liveness import LivenessRequest, LivenessResponse
from app.services.liveness import (
    passive_liveness_check,
    blink_liveness_check,
    head_turn_liveness_check,
    smile_liveness_check,
)

router = APIRouter(tags=["Liveness"])

@router.post("/liveness/check", response_model=LivenessResponse)
async def check_liveness(request: LivenessRequest):
    if isinstance(request.challenge_response, str) and request.challenge_type == "passive":
        return passive_liveness_check(request)
    elif isinstance(request.challenge_response, list) and request.challenge_type == "blink":
        return blink_liveness_check(request)
    elif isinstance(request.challenge_response, list) and request.challenge_type == "head_turn":
        return head_turn_liveness_check(request)
    elif isinstance(request.challenge_response, list) and request.challenge_type == "smile":
        return smile_liveness_check(request)
    else:
        raise HTTPException(status_code=400, detail="Invalid challenge response type or challenge type.")
