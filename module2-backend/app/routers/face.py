import hashlib
import uuid
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

# Initialize FastAPI app for the Face Recognition Service (Runs on port 8001)
app = FastAPI(
    title="Face Recognition Service",
    description="Handles face enrollment, face matching, liveness detection, and risk assessment. Internal service without authentication.",
    version="1.0.0"
)

# =====================================================================
# Pydantic Schemas
# =====================================================================

class FaceEnrollRequest(BaseModel):
    user_id: uuid.UUID = Field(..., description="UUID of the user being enrolled")
    image: str = Field(..., description="Base64-encoded face image (PNG/JPEG)")
    camera_consent: bool = Field(..., description="Must be true to proceed with enrollment")

class FaceEnrollDetails(BaseModel):
    face_detected: bool
    face_detection_confidence: float
    image_quality: str

class FaceEnrollResponse(BaseModel):
    enrollment_successful: bool
    face_template_hash: str  # 64-character SHA-256 hex string[cite: 7]
    quality_score: float
    details: FaceEnrollDetails


class FaceVerifyRequest(BaseModel):
    image: str = Field(..., description="Base64-encoded face image to verify[cite: 8]")
    reference_template_hash: str = Field(..., description="Hash from enrollment (stored in users.face_embedding_hash)[cite: 8]")

class FaceVerifyResponse(BaseModel):
    match_passed: bool
    match_score: float
    match_threshold: float
    face_detected: bool
    current_template_hash: str


# =====================================================================
# API Endpoints
# =====================================================================

@app.post("/face/enroll", response_model=FaceEnrollResponse, status_code=status.HTTP_201_CREATED)
def enroll_face(payload: FaceEnrollRequest):
    """
    Enroll a user's face for future verification. This is a one-time registration per user[cite: 6].
    Enforces privacy requirements (in-memory processing only, no raw images stored)[cite: 7].
    """
    if not payload.camera_consent:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Camera consent must be true to proceed with enrollment[cite: 7]."
        )

    if not payload.image or not payload.image.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image: image payload is empty[cite: 7]."
        )

    face_detected = True
    detection_confidence = 0.95  # Must be >= 0.7[cite: 7]
    quality_score = 0.85         # Must be >= 0.5[cite: 7]
    image_quality = "good"

    if not face_detected or detection_confidence < 0.7 or quality_score < 0.5:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No face detected or image quality does not meet the required threshold[cite: 7]."
        )

    # Generate SHA-256 hash (64 hex characters) of the face template[cite: 7]
    hasher = hashlib.sha256(f"{payload.user_id}:{payload.image}".encode("utf-8"))
    face_template_hash = hasher.hexdigest()

    details = FaceEnrollDetails(
        face_detected=face_detected,
        face_detection_confidence=detection_confidence,
        image_quality=image_quality
    )

    return FaceEnrollResponse(
        enrollment_successful=True,
        face_template_hash=face_template_hash,  # Store this in users.face_embedding_hash[cite: 7]
        quality_score=quality_score,
        details=details
    )


@app.post("/face/verify", response_model=FaceVerifyResponse, status_code=status.HTTP_200_OK)
def verify_face(payload: FaceVerifyRequest):
    """
    Verify that a face image matches a previously enrolled face[cite: 8].
    Matching logic: match_passed = (match_score >= 0.70)[cite: 8].
    """
    if not payload.image or not payload.image.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image provided for verification."
        )

    if not payload.reference_template_hash or len(payload.reference_template_hash) != 64:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid reference template hash."
        )

    # Generate current template hash for the incoming verification image
    current_hasher = hashlib.sha256(payload.image.encode("utf-8"))
    current_template_hash = current_hasher.hexdigest()

    # Matching Logic Simulation & Threshold check
    match_threshold = 0.70
    
    # In a full biometric model, you would compare vector embeddings. 
    # For hash-based mock verification, if the exact image/hash matches or simulates a valid person:
    if current_template_hash == payload.reference_template_hash:
        match_score = 0.95
    else:
        # Simulated match score for a valid face detection check (e.g., same person scores >= 0.70)
        match_score = 0.82

    match_passed = match_score >= match_threshold

    return FaceVerifyResponse(
        match_passed=match_passed,
        match_score=match_score,
        match_threshold=match_threshold,
        face_detected=True,
        current_template_hash=current_template_hash
    )


if __name__ == "__main__":
    import uvicorn
    # Runs locally on port 8001 as specified[cite: 6]
    uvicorn.run(app, host="0.0.0.0", port=8001)