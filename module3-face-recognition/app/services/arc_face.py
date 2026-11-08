"""
Extract face embedding/features for hashing.
We will use ArcFace as our face recognition model for extracting embeddings.
Return numpy array that can be hashed using SimHash.
"""

from functools import lru_cache
import os
from threading import Lock
import cv2
import numpy as np
from insightface.app import FaceAnalysis

ARCFACE_MODEL_NAME = "buffalo_l"
ARCFACE_MODEL_ROOT = os.getenv("INSIGHTFACE_HOME", "~/.insightface")
ARCFACE_PROVIDERS = ["CPUExecutionProvider"]
ARCFACE_DETECTION_SIZE = (640, 640)  
ARCFACE_CONTEXT_ID = -1   #GPU context ID, -1 for CPU
ARCFACE_LOCK = Lock()


"""Get the ArcFace model instance with caching to avoid reloading the model multiple times."""
@lru_cache(maxsize=1)
def get_arcface_model():
    arcface_model = FaceAnalysis(
        name=ARCFACE_MODEL_NAME,
        root=ARCFACE_MODEL_ROOT,
        providers=ARCFACE_PROVIDERS,
    )
    arcface_model.prepare(ctx_id=ARCFACE_CONTEXT_ID, det_size=ARCFACE_DETECTION_SIZE)
    return arcface_model

"""Extract a normalized ArcFace embedding from an RGB image."""
def extract_face_embedding(image_array, _detection):
    arcface_model = get_arcface_model()

    image_bgr = cv2.cvtColor(image_array, cv2.COLOR_RGB2BGR) #Convert RGB image to BGR for OpenCV processing
    with ARCFACE_LOCK:
        faces = arcface_model.get(image_bgr)

    if not faces:
        return None

    embedding = faces[0].embedding

    if embedding is None:
        return None

    embedding = np.asarray(embedding, dtype=np.float32)
    norm = np.linalg.norm(embedding)

    if norm == 0:
        return None

    return embedding / norm
