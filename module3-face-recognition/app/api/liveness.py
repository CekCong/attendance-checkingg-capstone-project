# =============================================================================
# LIVENESS DETECTION ENDPOINT (REQUIRED - partial; BONUS for advanced)
# =============================================================================
from fastapi import APIRouter, HTTPException
from app.schemas.liveness import LivenessRequest, LivenessResponse
from app.services.arc_face import extract_face_embedding
from app.services.sim_hash import generate_face_hash
from app.services.image_decoder import decode_base64_image
from app.services.face_detector import detect_face
from app.services.liveness import analyze_face_mesh, detect_blink, detect_head_turn
from app.services.face_quality import calculate_quality_score

router = APIRouter(tags=["Liveness"])

LIVENESS_THRESHOLD = 0.60
TARGET_FACE_AREA_RATIO = 0.20
CONFIDENCE_WEIGHT = 0.40
IMAGE_QUALITY_WEIGHT = 0.30
FACE_SIZE_WEIGHT = 0.30
SUPPORTED_CHALLENGES = {"passive", "blink", "head_turn"}

@router.post("/liveness/check", response_model=LivenessResponse)
async def check_liveness(request: LivenessRequest):
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
    if request.challenge_type not in SUPPORTED_CHALLENGES:
        raise HTTPException(status_code=400, detail="Unsupported challenge type.")

    # 1. Decode base64 image to numpy array
    try:
        image = decode_base64_image(request.challenge_response)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Base64 image.")
    
    # 2. Detect face using MediaPipe FaceDetection
    try:
        face = detect_face(image)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Face detection failed.") from exc

    # 3. If no face detected, return with liveness_passed=False
    if not face:
        return LivenessResponse(
            liveness_passed=False,
            liveness_score=0.0,
            liveness_threshold=LIVENESS_THRESHOLD,
            face_embedding_hash="",
            details={"error": "No face detected or multiple faces detected."}
        )
    # 4. Analyze face for liveness signals:
    confidence_score = float(face["confidence"])  # Confidence score from face detection
    image_quality_score = calculate_quality_score(image, face)

    bbox = face["bounding_box"]
    face_ratio = max(0.0, bbox["width"]) * max(0.0, bbox["height"])

    face_size_score = min(face_ratio / TARGET_FACE_AREA_RATIO, 1.0)

    # Keep landmark objects internal because they are not JSON serializable.
    try:
        mesh_result = analyze_face_mesh(image)
    except Exception:
        mesh_result = {
            "face_mesh_complete": False,
            "landmark_count": 0,
            "nose_tip_z": None,
            "depth_quality": "poor",
            "landmarks": None,
        }
    landmarks = mesh_result.pop("landmarks", None)
    blink_detected = detect_blink(landmarks) if request.challenge_type == "blink" else False
    head_turn_detected = (
        detect_head_turn(landmarks) if request.challenge_type == "head_turn" else False
    )

    # 5. Calculate liveness_score (0.0 to 1.0)
    liveness_score = (
        confidence_score * CONFIDENCE_WEIGHT
        + image_quality_score * IMAGE_QUALITY_WEIGHT
        + face_size_score * FACE_SIZE_WEIGHT
    )
    liveness_score = round(max(0.0, min(liveness_score, 1.0)), 4)

    # 6. liveness_passed = (liveness_score >= 0.60)
    liveness_passed = liveness_score >= LIVENESS_THRESHOLD
    if request.challenge_type == "blink":
        liveness_passed = liveness_passed and blink_detected
    elif request.challenge_type == "head_turn":
        liveness_passed = liveness_passed and head_turn_detected

    # 7. Generate face embedding hash
    face_embedding = extract_face_embedding(image, face)

    if face_embedding is None:
        return LivenessResponse(
            liveness_passed=False,
            liveness_score=liveness_score,
            liveness_threshold=LIVENESS_THRESHOLD,
            face_embedding_hash="",
            details={"error": "Failed to extract face embedding."}
        )

    face_embedding_hash = generate_face_hash(face_embedding)

    return LivenessResponse(
        liveness_passed=liveness_passed,
        liveness_score=liveness_score,
        liveness_threshold=LIVENESS_THRESHOLD,
        face_embedding_hash=face_embedding_hash,
        details={
            "confidence_score": confidence_score,
            "image_quality_score": image_quality_score,
            "face_size_score": face_size_score,
            "challenge_type": request.challenge_type,
            "blink_detected": blink_detected,
            "head_turn_detected": head_turn_detected,
            **mesh_result
        }
    )
