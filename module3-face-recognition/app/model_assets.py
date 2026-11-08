"""Pinned official MediaPipe assets, verified before installation and loading."""
import hashlib


MODEL_ASSETS = {
    "blaze_face_short_range.tflite": (
        "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
        "b4578f35940bf5a1a655214a1cce5cab13eba73c1297cd78e1a04c2380b0152f",
    ),
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
        "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    ),
}


def verify_model(name, data):
    digest = hashlib.sha256(data).hexdigest()
    if digest != MODEL_ASSETS[name][1]:
        raise RuntimeError(f"MediaPipe model checksum mismatch: {name}")
    return digest
