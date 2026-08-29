from fastapi import APIRouter, HTTPException
from app.schemas.face import FaceEnrollRequest, FaceEnrollResponse, FaceVerifyRequest,  FaceVerifyResponse
from app.services.arc_face import extract_face_embedding
from app.services.biohashing import generate_face_hash
from app.services.image_decoder import decode_base64_image
from app.services.face_detector import detect_face
from app.services.face_quality import calculate_quality_score
from app.services.similarity import hamming_distance

router = APIRouter(tags=["Face"])

# =============================================================================
# FACE ENROLLMENT ENDPOINT (REQUIRED - 4 points in public tests)
# =============================================================================

@router.post("/face/enroll", response_model=FaceEnrollResponse, status_code=201)
async def enroll_face(request: FaceEnrollRequest):
    """
    Enroll a user's face for future verification.
    Takes in a base64 image, user ID, and camera consent, returns a hash of the face template.

    Success Criteria:
    - Face detected with confidence >= 0.7
    - Quality score >= 0.5
    - Returns 64-char SHA-256 hex hash
    """

    # 1. Validate camera_consent is True (return 400 if False)
    if not request.camera_consent:
            raise HTTPException(status_code=400, detail="Camera consent is required for enrollment.")

    #2. Decode base64 image to numpy array
    try:
        image = decode_base64_image(request.image)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # 3. Detect face using MediaPipe FaceDetection
    try:
        face_detected = detect_face(image)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Face detection failed: " + str(e))

    # 4. If no face detected, return 400 with "No face detected"
    if not face_detected:
        raise HTTPException(status_code=400, detail="No face detected in the image.")

    if face_detected['confidence'] < 0.7:
        raise HTTPException(status_code=400, detail="Face detection confidence is too low for enrollment.")
    
    # 5. Extract face features/embedding
    embedding = extract_face_embedding(image, face_detected)

    if embedding is None:
        raise HTTPException(status_code=500, detail="Failed to extract face embedding.")
    
    # 6. Generate hash of embedding (64 hex chars)
    face_hash = generate_face_hash(embedding, user_id=request.user_id)  

    #7. Calculate quality score based on:
    #   - Face detection confidence
    #   - Image resolution
    #   - Face size relative to image
    quality_score=calculate_quality_score(image, face_detected)

    if quality_score < 0.5:
        raise HTTPException(status_code=400, detail="Face quality score is too low for enrollment.")

    # 8. Return enrollment response
    del embedding
    del image

    return FaceEnrollResponse(
        enrollment_successful=True,
        face_template_hash=face_hash,
        quality_score=quality_score,
        details={"message": "Face enrolled successfully."}
    )



# =============================================================================
# FACE VERIFICATION ENDPOINT (REQUIRED - 4 points in public tests)
# =============================================================================

@router.post("/face/verify", response_model=FaceVerifyResponse)
async def verify_face(request: FaceVerifyRequest):
    """
    Verify a face against an enrolled template.
    Takes in a base64 image and a reference hash, returns match score and pass/fail.

    1. Decode base64 image to numpy array
    2. Detect face using MediaPipe FaceDetection
    3. If no face detected, return with face_detected=False
    4. Extract face features/embedding
    5. Generate SHA-256 hash of current face
    6. Compare hashes or embeddings (choose your approach)
    7. Calculate match_score (0.0 to 1.0)
    8. match_passed = (match_score >= 0.70)

    Note: Hash comparison alone gives binary match. For continuous
    scores, consider perceptual hashing or embedding similarity.
    """
    # 1. Decode base64 image to numpy array
    try:
        image = decode_base64_image(request.image)
    except Exception as e:
        raise HTTPException(status_code=400, detail="Could not decode image: " + str(e))

    # 2. Detect face using MediaPipe FaceDetection
    try:
        face_detected = detect_face(image)
    except Exception as e:
        raise HTTPException(status_code=500, detail="Face detection failed: " + str(e))

    # 3. If no face detected, return with face_detected=False
    if not face_detected or face_detected["confidence"] < 0.7:
        return FaceVerifyResponse(
            match_passed=False,
            match_score=0.0,
            match_threshold=0.70,
            face_detected=False,
            current_template_hash=""
        )
    
    # 4. Extract face features/embedding
    embedding = extract_face_embedding(image, face_detected)

    if embedding is None:
        raise HTTPException(status_code=500, detail="Failed to extract face embedding.")

    # 5. Generate BioHash of current embedding
    current_hash = generate_face_hash(embedding, request.user_id) 

    # 6. Compare hashes or embeddings (Hamming distance)
    distance =  hamming_distance(current_hash, request.reference_template_hash)

    # 7. Calculate match_score (0.0 to 1.0)
    num_bits = len(current_hash) 
    match_score = 1.0 - (distance/num_bits)  # Normalize to [0,1]

    # 8. match_passed = (match_score >= 0.70)
    match_passed = match_score >= 0.70

    del embedding
    del image

    return FaceVerifyResponse(
        match_passed=match_passed,
        match_score=match_score,
        match_threshold=0.70,
        face_detected=True,
        current_template_hash=current_hash
    )


@router.post("/face/match")
async def match_face(request: FaceVerifyRequest):
    """
    Legacy face matching endpoint. Redirects to /face/verify.
    Kept for backwards compatibility.
    """
    return await verify_face(request)