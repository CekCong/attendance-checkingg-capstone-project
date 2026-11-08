"""Preparation feedback only: no identity matching, templates, or stored images."""
import numpy as np

from app.services.face_detector import detect_face
from app.services.face_quality import calculate_quality_score
from app.services.mediapipe_tasks import landmarks


def camera_readiness(image):
    face = detect_face(image)
    if not face:
        return {"ready": False, "message": "Keep exactly one face visible. Face the camera and move into even lighting.", "warnings": []}
    box = face["bounding_box"]
    x, y, w, h = (box[k] for k in ("x_min", "y_min", "width", "height"))
    if x < 0 or y < 0 or x + w > 1 or y + h > 1:
        return {"ready": False, "message": "Your face is partly outside the picture. Move back and keep your whole face in view.", "warnings": []}
    if w * h < 0.04:
        return {"ready": False, "message": "Move a little closer so your face is easier to read.", "warnings": []}
    if face["confidence"] < 0.70 or calculate_quality_score(image, face) < 0.50:
        return {"ready": False, "message": "The picture is not clear enough yet. Hold the camera steady and face a light source.", "warnings": []}
    if not landmarks(image):
        return {"ready": False, "message": "Your eyes and mouth are not clear enough. Look straight ahead and keep your face uncovered.", "warnings": []}

    height, width = image.shape[:2]
    crop = image[int(y * height):int((y + h) * height), int(x * width):int((x + w) * width)]
    # Lighting is advisory: exposure/skin tone alone must not block a readable face.
    brightness = float(np.mean(crop @ np.array([0.2126, 0.7152, 0.0722])))
    warnings = []
    if brightness < 45:
        warnings.append("Your face looks dim. A light in front of you may improve the recording.")
    elif brightness > 225:
        warnings.append("Your face looks very bright. Reduce direct light or glare if possible.")
    return {"ready": True, "message": "Your face is visible and the camera is ready.", "warnings": warnings}
