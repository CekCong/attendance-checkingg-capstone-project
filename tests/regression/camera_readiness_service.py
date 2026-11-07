"""Run with: docker compose exec -T face-recognition python < this_file"""
import unittest
from unittest.mock import patch
import numpy as np
from app.services import camera_readiness as service


class CameraReadinessTests(unittest.TestCase):
    def check(self, *, face=True, brightness=128, mesh=True, **box_changes):
        detection = {'confidence': .95, 'bounding_box': {
            'x_min': .3, 'y_min': .2, 'width': .4, 'height': .5, **box_changes}}
        with patch.object(service, 'detect_face', return_value=detection if face else None), \
             patch.object(service, 'landmarks', return_value=[object()] * 468 if mesh else None):
            return service.camera_readiness(np.full((480, 640, 3), brightness, dtype=np.uint8))

    def test_clear_face_is_ready(self):
        self.assertEqual(self.check(), {'ready': True, 'message': 'Your face is visible and the camera is ready.', 'warnings': []})

    def test_missing_or_multiple_faces(self):
        result = self.check(face=False)
        self.assertFalse(result['ready'])
        self.assertIn('exactly one face', result['message'])

    def test_clipped_small_or_unreadable_face(self):
        for args in ({'x_min': -.1}, {'width': .1, 'height': .1}, {'mesh': False}):
            with self.subTest(args=args):
                self.assertFalse(self.check(**args)['ready'])

    def test_lighting_is_advisory_for_readable_faces(self):
        for brightness in (20, 240):
            with self.subTest(brightness=brightness):
                result = self.check(brightness=brightness)
                self.assertTrue(result['ready'])
                self.assertEqual(len(result['warnings']), 1)


if __name__ == '__main__':
    unittest.main()
