"""Real model compatibility. Run explicitly with the Stage 6 face dependencies/models.

Sample images do not establish positive live-person acceptance or attack resistance.
"""
import os
from pathlib import Path
import subprocess
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]


def face_python(source):
    env = {**os.environ, 'SAMPLE_IMAGES_DIR':str(ROOT / 'sample_images')}
    result = subprocess.run([sys.executable, '-c', source], cwd=ROOT / 'module3-face-recognition',
                            env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_arcface_numpy_and_onnx_compatibility():
    face_python('''
from PIL import Image
import numpy as np
import os
from pathlib import Path
from app.services.arc_face import extract_face_embedding
root = Path(os.environ['SAMPLE_IMAGES_DIR'])
embeddings = []
for name in ['obama.jpg', 'obama2.jpg', 'biden.jpg']:
    value = extract_face_embedding(np.asarray(Image.open(root / name).convert('RGB')), None)
    assert value is not None and value.shape == (512,) and np.isfinite(value).all()
    assert abs(np.linalg.norm(value)-1) < 1e-5
    embeddings.append(value)
assert float(embeddings[0] @ embeddings[1]) > 0.5
assert float(embeddings[0] @ embeddings[2]) < 0.3
''')


def test_tasks_real_face_mesh_and_no_face():
    face_python('''
from PIL import Image
import numpy as np
import os
from pathlib import Path
from app.services.face_detector import detect_face
from app.services.liveness import analyze_face_mesh, calculate_ear, LEFT_EYE_INDICES
from app.services.mediapipe_tasks import get_tasks, close_tasks
get_tasks()  # Missing model artifacts must fail, never silently skip or download.
try:
    image = np.asarray(Image.open(Path(os.environ['SAMPLE_IMAGES_DIR']) / 'obama.jpg').convert('RGB'))
    face = detect_face(image)
    assert face and face['confidence'] >= 0.5
    assert 0 < face['bounding_box']['width'] <= 1
    assert 0 < face['bounding_box']['height'] <= 1
    mesh = analyze_face_mesh(image)
    assert mesh['face_mesh_complete'] and mesh['landmark_count'] >= 468
    assert np.isfinite(mesh['nose_tip_z'])
    assert 0 < calculate_ear(mesh['landmarks'], LEFT_EYE_INDICES) < 1
    empty = np.zeros((480,640,3),dtype=np.uint8)
    assert detect_face(empty) is None
    assert not analyze_face_mesh(empty)['face_mesh_complete']
finally:
    close_tasks()
''')


@pytest.mark.parametrize('corrupt', [False, True])
def test_tasks_reject_missing_or_corrupt_models_before_native_loading(corrupt):
    face_python('''
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from app.services import mediapipe_tasks as tasks
with TemporaryDirectory() as directory:
    root = Path(directory)
    if CORRUPT:
        for name in ['blaze_face_short_range.tflite', 'face_landmarker.task']:
            (root / name).write_bytes(b'corrupt model')
    with patch.object(tasks, 'MODEL_ROOT', root), patch.object(
        tasks.mp.tasks.vision.FaceDetector, 'create_from_options'
    ) as create:
        try:
            tasks.get_tasks()
        except RuntimeError as error:
            assert ('checksum mismatch' if CORRUPT else 'missing') in str(error)
        else:
            raise AssertionError('Invalid assets were accepted')
        create.assert_not_called()
'''.replace('CORRUPT', repr(corrupt)))


def test_failed_download_preserves_existing_model_and_removes_temporary_file():
    face_python('''
import os
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from app import prepare_models
with TemporaryDirectory() as directory:
    root = Path(directory)
    target = root / 'blaze_face_short_range.tflite'
    target.write_bytes(b'existing artifact')
    with patch.dict(os.environ, MEDIAPIPE_MODEL_DIR=directory), patch.object(
        prepare_models.urllib.request, 'urlopen', return_value=BytesIO(b'bad download')
    ):
        try:
            prepare_models.main()
        except RuntimeError as error:
            assert 'checksum mismatch' in str(error)
        else:
            raise AssertionError('Invalid download was installed')
    assert target.read_bytes() == b'existing artifact'
    assert list(root.iterdir()) == [target]
''')
