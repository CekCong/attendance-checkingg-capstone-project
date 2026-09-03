"""
    Extract face embedding/features for hashing.

    TODO: Choose your approach:
    - Simple: Crop face region, resize to standard size, flatten
    - Advanced: Use MediaPipe Face Mesh landmarks
    - Even more advanced: Use face recognition model (dlib, etc.)

    Return numpy array that can be hashed.
"""

# We will use ArcFace as our face recognition model for extracting embeddings.

from functools import lru_cache
import os

import cv2
import numpy as np
from insightface.app import FaceAnalysis

ARCFACE_MODEL_NAME = "buffalo_l"
ARCFACE_MODEL_ROOT = os.getenv("INSIGHTFACE_HOME", "~/.insightface")
ARCFACE_PROVIDERS = ["CPUExecutionProvider"]
ARCFACE_DETECTION_SIZE = (640, 640)
ARCFACE_CONTEXT_ID = -1


@lru_cache(maxsize=1)
def get_arcface_model():
    arcface_model = FaceAnalysis(
        name=ARCFACE_MODEL_NAME,
        root=ARCFACE_MODEL_ROOT,
        providers=ARCFACE_PROVIDERS,
    )
    arcface_model.prepare(ctx_id=ARCFACE_CONTEXT_ID, det_size=ARCFACE_DETECTION_SIZE)
    return arcface_model


def extract_face_embedding(image_array, detection):
    arcface_model = get_arcface_model()

    image_height, image_width = image_array.shape[:2]
    bbox = detection["bounding_box"]

    # MediaPipe use relative coordinates, so we need to convert them to absolute pixel values
    x1 = int(bbox["x_min"] * image_width)
    y1 = int(bbox["y_min"] * image_height)
    x2 = int((bbox["x_min"] + bbox["width"]) * image_width)
    y2 = int((bbox["y_min"] + bbox["height"]) * image_height)

    x1 = max(0, min(x1, image_width))
    y1 = max(0, min(y1, image_height))
    x2 = max(0, min(image_width, x2))
    y2 = max(0, min(image_height, y2))

    if x1 >= x2 or y1 >= y2:
        return None

    face_crop = image_array[y1:y2, x1:x2]

    if face_crop.size == 0:
        return None

    # PIL decoding produces RGB arrays; InsightFace expects OpenCV BGR input.
    face_crop_bgr = cv2.cvtColor(face_crop, cv2.COLOR_RGB2BGR)
    faces = arcface_model.get(face_crop_bgr)

    if not faces:
        return None

    embedding = faces[0].embedding

    if embedding is None:
        return None

    embedding = np.asarray(
        embedding,
        dtype=np.float32
    )

    norm = np.linalg.norm(embedding)

    if norm == 0:
        return None

    return embedding / norm
