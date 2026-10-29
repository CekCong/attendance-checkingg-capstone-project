"""Install versioned official MediaPipe models over verified HTTPS, outside requests."""
import hashlib
import os
from pathlib import Path
import tempfile
import urllib.request

MODEL_URLS = {
    "blaze_face_short_range.tflite": "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}


def main():
    root = Path(os.getenv("MEDIAPIPE_MODEL_DIR", "/app/models/mediapipe"))
    root.mkdir(parents=True, exist_ok=True)
    for name, url in MODEL_URLS.items():
        target = root / name
        # Explicit preparation may refresh a corrupt/partial local model atomically.
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
            temporary = Path(output.name)
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read(32 * 1024 * 1024)
                if not data or len(data) == 32 * 1024 * 1024:
                    raise RuntimeError("Unexpected model size")
                output.write(data)
                output.flush()
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        print(name, hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
