"""
Calculate a quality score for the detected face based on:
- Face detection confidence
- Image resolution
- Face size relative to image

Returns a float between 0 and 1.

Calculation logic (designed by myself):

Quality Score =
    (Face Detection Confidence * 0.50) + (Image Resolution Score * 0.25) + (Face Size Score * 0.25)

Reasoning:
Face detection confidence gets the highest importance,
while resolution and face size provide supporting evidence.
"""

BASELINE_RESOLUTION = 640 * 480
TARGET_FACE_AREA_RATIO = 0.20
CONFIDENCE_WEIGHT = 0.50
RESOLUTION_WEIGHT = 0.25
FACE_SIZE_WEIGHT = 0.25


def calculate_quality_score(image, face_detected):

    height, width = image.shape[:2]

    # 1. Face Detection Confidence Score (0 to 1)
    confidence_score = face_detected["confidence"]

    # 2. Image Resolution Score (0 to 1)
    # 640x480 or higher receives the maximum score
    image_resolution = width * height

    resolution_score = min(image_resolution / BASELINE_RESOLUTION, 1.0)

    # 3. Face Size Score (0 to 1)
    bbox = face_detected["bounding_box"]

    # MediaPipe bbox width and height are relative values
    # Example: 0.4 * 0.5 = face occupies 20% of image
    face_ratio = bbox["width"] * bbox["height"]

    # Assume a face occupying 20% of the image
    # receives the maximum face-size score
    face_size_score = min(face_ratio / TARGET_FACE_AREA_RATIO, 1.0)

    # 4. Final quality score
    quality_score = (
        confidence_score * CONFIDENCE_WEIGHT
        + resolution_score * RESOLUTION_WEIGHT
        + face_size_score * FACE_SIZE_WEIGHT
    )

    return round(quality_score, 3)
