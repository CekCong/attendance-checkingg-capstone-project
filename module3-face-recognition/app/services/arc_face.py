"""
    Extract face embedding/features for hashing.

    TODO: Choose your approach:
    - Simple: Crop face region, resize to standard size, flatten
    - Advanced: Use MediaPipe Face Mesh landmarks
    - Even more advanced: Use face recognition model (dlib, etc.)

    Return numpy array that can be hashed.
"""

# We will use ArcFace as our face recognition model for extracting embeddings.

import cv2
import numpy as np
from functools import lru_cache
from insightface.app import FaceAnalysis

#--------Store the model in memory to avoid reloading it for each request--------#
@lru_cache(maxsize=1)
def get_arcface_model():
    arcface_model = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    arcface_model.prepare(ctx_id=0, det_size=(640, 640))
    return arcface_model

def extract_face_embedding(image_array, detection):
    arcface_model = get_arcface_model()

    image_height, image_width = image_array.shape[:2]
    bbox = detection["bbox"]

    x = int(bbox["x"])
    y = int(bbox["y"])
    width = int(bbox["width"])
    height = int(bbox["height"])

    x1 = max(0, x)
    y1 = max(0, y)

    x2 = min(image_width, x + width)
    y2 = min(image_height, y + height)

    face_crop = image_array[y1:y2, x1:x2]

    if face_crop.size == 0:
        return None

    faces = arcface_model.get(face_crop)

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
   