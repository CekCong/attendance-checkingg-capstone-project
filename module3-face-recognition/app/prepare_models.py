"""Install versioned official MediaPipe models over verified HTTPS, outside requests."""
import os
from pathlib import Path
import tempfile
import urllib.request

from .model_assets import MODEL_ASSETS, verify_model


def main():
    root = Path(os.getenv("MEDIAPIPE_MODEL_DIR", "/app/models/mediapipe"))
    root.mkdir(parents=True, exist_ok=True)
    for name, (url, _) in MODEL_ASSETS.items():
        target = root / name
        # Explicit preparation may refresh a corrupt/partial local model atomically.
        with tempfile.NamedTemporaryFile(dir=root, delete=False) as output:
            temporary = Path(output.name)
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    data = response.read(32 * 1024 * 1024)
                if not data or len(data) == 32 * 1024 * 1024:
                    raise RuntimeError("Unexpected model size")
                digest = verify_model(name, data)
                output.write(data)
                output.flush()
                os.replace(temporary, target)
            finally:
                temporary.unlink(missing_ok=True)
        print(name, digest)


if __name__ == "__main__":
    main()
