"""MediaPipe Tasks adapters. Models are installed explicitly before service startup."""
from functools import lru_cache
import os
from pathlib import Path
from threading import Lock

import mediapipe as mp
import numpy as np
from app.model_assets import verify_model

MODEL_ROOT = Path(os.getenv("MEDIAPIPE_MODEL_DIR", "/app/models/mediapipe"))
_TASK_LOCK = Lock()


@lru_cache(maxsize=1)
def get_tasks():
    paths = [MODEL_ROOT / "blaze_face_short_range.tflite", MODEL_ROOT / "face_landmarker.task"]
    if not all(path.is_file() for path in paths):
        raise RuntimeError("MediaPipe models are missing. Run python -m app.prepare_models before starting the service.")
    for path in paths:
        verify_model(path.name, path.read_bytes())
    base = mp.tasks.BaseOptions
    vision = mp.tasks.vision
    detector = vision.FaceDetector.create_from_options(vision.FaceDetectorOptions(
        base_options=base(model_asset_path=str(paths[0])), min_detection_confidence=0.5,
    ))
    try:
        landmarker = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=base(model_asset_path=str(paths[1])), num_faces=1,
            min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
        ))
    except Exception:
        detector.close()
        raise
    return detector, landmarker


def _image(array):
    return mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(array))


def detect(array):
    # The shared synchronous Tasks instances are serialized across request threads.
    with _TASK_LOCK:
        return get_tasks()[0].detect(_image(array))


def landmarks(array):
    with _TASK_LOCK:
        result = get_tasks()[1].detect(_image(array))
    return result.face_landmarks[0] if result.face_landmarks else None


def close_tasks():
    if get_tasks.cache_info().currsize:
        for task in get_tasks(): task.close()
        get_tasks.cache_clear()
