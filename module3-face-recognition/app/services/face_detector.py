"""
    Detect faces in an image using MediaPipe.

    Raises ValueError if the input is not a valid numpy array.

    Mediapipe.solutions.face_detection.FaceDetection, setting min_detection_confidence=0.5

    Return None if no face is detected or more than one face is detected.

    Return detection results with confidence scores, bbox coordinates for qulity score calculation. 
"""

import mediapipe
import numpy as np

MIN_DETECTION_CONFIDENCE = 0.5
MAX_DETECTED_FACES = 1


def detect_face(image_array):
   
    if not isinstance(image_array, np.ndarray):
        raise ValueError("Input must be a numpy array.")

    with mediapipe.solutions.face_detection.FaceDetection(
        min_detection_confidence=MIN_DETECTION_CONFIDENCE
    ) as detector:
        results = detector.process(image_array)

    # No face detected or more than one face detected
    if not results.detections or len(results.detections) > MAX_DETECTED_FACES:
        return None

    face = results.detections[0]

    confidence = float(face.score[0])

    bbox = face.location_data.relative_bounding_box

    return {
        "confidence": confidence,
        "bounding_box": {
            "x_min": bbox.xmin,
            "y_min": bbox.ymin,
            "width": bbox.width,
            "height": bbox.height
        }
    }
