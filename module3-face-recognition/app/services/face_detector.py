"""Return one MediaPipe Tasks face detection with a normalized bounding box."""
import numpy as np
from app.services.mediapipe_tasks import detect


def detect_face(image_array):
    if not isinstance(image_array, np.ndarray):
        raise ValueError("Input must be a numpy array.")
    results = detect(image_array)
    if len(results.detections) != 1:
        return None
    face = results.detections[0]
    bbox = face.bounding_box
    height, width = image_array.shape[:2]
    return {
        "confidence": float(face.categories[0].score),
        "bounding_box": {"x_min": bbox.origin_x / width, "y_min": bbox.origin_y / height,
                         "width": bbox.width / width, "height": bbox.height / height},
    }
