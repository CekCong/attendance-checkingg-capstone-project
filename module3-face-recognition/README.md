## Key Endpoints — Module 3: Face Recognition & Risk Service

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Returns service information and lists available endpoints |
| `GET` | `/health` | Checks whether the Face Recognition service is running |
| `POST` | `/face/enroll` | Enrolls a user's face and generates a protected face template |
| `POST` | `/face/verify` | Verifies a captured face against an enrolled face template |
| `POST` | `/face/match` | Legacy face matching endpoint; uses `/face/verify` |
| `POST` | `/liveness/check` | Performs liveness detection to detect spoofing attempts |
| `POST` | `/risk/assess` | Calculates a risk score using face match, liveness, device, network, and geolocation signals |


"""
SAIV Face Recognition & Risk Service - Module 3

This is the skeleton implementation for the Face Recognition module.
Students must implement face enrollment, verification, liveness detection,
and risk scoring.

Privacy Requirements:
- NO raw face images should be stored
- Process images in-memory only
- Store only SHA-256 hashes of face embeddings

Recommended Libraries:
- MediaPipe: Face detection and 468-landmark face mesh
- OpenCV: Image processing
- Pillow: Image loading from base64
- NumPy: Numerical operations
"""


# =============================================================================
# PRIVACY REQUIREMENTS (IMPORTANT!)
# =============================================================================
"""
Your implementation MUST follow these privacy requirements:

1. NO RAW IMAGES STORED
   - Process images in-memory only
   - Do not write images to disk
   - Do not send images to external APIs

2. HASH-ONLY STORAGE
   - Store only SHA-256 hashes (64 hex characters)
   - Hashes are one-way - cannot reconstruct face
   - Different faces must produce different hashes

3. EPHEMERAL PROCESSING
   - Clear image data after processing
   - No caching of raw biometric data
   - Use Python's memory management (del, gc.collect)

4. CONSENT TRACKING
   - Require camera_consent=True for enrollment
   - Log consent in audit trail (backend responsibility)

5. RESPONSE HYGIENE
   - Never include base64 image data in responses
   - Only return hashes, scores, and metadata
"""