import mediapipe as mp
import numpy as np

EAR_THRESHOLD = 0.25
FACE_MESH_MAX_FACES = 1
FACE_MESH_MIN_CONFIDENCE = 0.5
EXPECTED_LANDMARK_COUNT = 468
GOOD_DEPTH_THRESHOLD = 0.05
MODERATE_DEPTH_THRESHOLD = 0.02
LEFT_EYE_INDICES = (33, 160, 158, 133, 153, 144)
RIGHT_EYE_INDICES = (362, 385, 387, 263, 373, 380)
LEFT_FACE_EDGE_INDEX = 234
RIGHT_FACE_EDGE_INDEX = 454
NOSE_TIP_INDEX = 1
HEAD_TURN_RATIO_THRESHOLD = 0.18

"""
    Analyze face using MediaPipe Face Mesh (BONUS).

    TODO: Implement using:
    - mediapipe.solutions.face_mesh.FaceMesh
    - Extract 468 landmarks
    - Calculate depth from nose_tip_z (landmark index 1)
    - Check mesh completeness

    Return dict with:
    - face_mesh_complete: bool
    - landmark_count: int
    - nose_tip_z: float
    - depth_quality: "good" | "moderate" | "poor"
 """



def analyze_face_mesh(image_array):

    if image_array is None:
        raise ValueError("Input image array is None")

    mp_face_mesh = mp.solutions.face_mesh

    # MediaPipe expects images in RGB format

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=FACE_MESH_MAX_FACES,
        refine_landmarks=False,
        min_detection_confidence=FACE_MESH_MIN_CONFIDENCE,
    ) as face_mesh:

        results = face_mesh.process(image_array)

    # Check if any face landmarks were detected
    if not results.multi_face_landmarks:
        return {
            "face_mesh_complete": False,
            "landmark_count": 0,
            "nose_tip_z": None,
            "depth_quality": "poor",
            "landmarks": None
        }

    landmarks = results.multi_face_landmarks[0].landmark
    landmark_count = len(landmarks)

    # 468 landmarks in total for a complete face mesh
    face_mesh_complete = landmark_count >= EXPECTED_LANDMARK_COUNT

    nose_tip_z = float(landmarks[NOSE_TIP_INDEX].z)

    depth = abs(nose_tip_z)

    if depth >= GOOD_DEPTH_THRESHOLD:
        depth_quality = "good"
    elif depth >= MODERATE_DEPTH_THRESHOLD:
        depth_quality = "moderate"
    else:
        depth_quality = "poor"

    return {
        "face_mesh_complete": face_mesh_complete,
        "landmark_count": landmark_count,
        "nose_tip_z": nose_tip_z,
        "depth_quality": depth_quality,
        "landmarks": landmarks
    }


"""
    Detect eye blink from face mesh landmarks (BONUS).

    TODO: Implement using:
    - Eye landmark indices (see MediaPipe docs)
    - Calculate Eye Aspect Ratio (EAR)
    - EAR < threshold indicates closed eye
"""

# Detect blink based on Eye Aspect Ratio (EAR). EAR < threshold --> closed eye
def detect_blink(face_mesh_landmarks):

    if face_mesh_landmarks is None:
        return False

    left_ear = calculate_ear(face_mesh_landmarks, LEFT_EYE_INDICES)
    right_ear = calculate_ear(face_mesh_landmarks, RIGHT_EYE_INDICES)


    # Average EAR for both eyes
    avg_ear = (left_ear + right_ear) / 2.0

    return avg_ear < EAR_THRESHOLD


def detect_head_turn(face_mesh_landmarks):
    """Detect horizontal head rotation from nose displacement."""
    if face_mesh_landmarks is None:
        return False

    left_x = float(face_mesh_landmarks[LEFT_FACE_EDGE_INDEX].x)
    right_x = float(face_mesh_landmarks[RIGHT_FACE_EDGE_INDEX].x)
    nose_x = float(face_mesh_landmarks[NOSE_TIP_INDEX].x)
    half_width = abs(right_x - left_x) / 2.0

    if half_width == 0:
        return False

    face_center_x = (left_x + right_x) / 2.0
    turn_ratio = abs(nose_x - face_center_x) / half_width
    return turn_ratio >= HEAD_TURN_RATIO_THRESHOLD


"""Helper function to calculate Eye Aspect Ratio (EAR).

EAR is a measure of eye openness calculated using specific eye landmarks.
"""
def calculate_ear(landmarks, indices):
    p1 = landmarks[indices[0]]
    p2 = landmarks[indices[1]]
    p3 = landmarks[indices[2]]
    p4 = landmarks[indices[3]]
    p5 = landmarks[indices[4]]
    p6 = landmarks[indices[5]]

    # Convert landmarks into x, y coordinates
    p1 = np.array([p1.x, p1.y])
    p2 = np.array([p2.x, p2.y])
    p3 = np.array([p3.x, p3.y])
    p4 = np.array([p4.x, p4.y])
    p5 = np.array([p5.x, p5.y])
    p6 = np.array([p6.x, p6.y])

    vertical_1 = np.linalg.norm(p2 - p6)
    vertical_2 = np.linalg.norm(p3 - p5)

    horizontal = np.linalg.norm(p1 - p4)

    if horizontal == 0:
        return 0.0

    ear = (vertical_1 + vertical_2) / (2.0 * horizontal)

    return ear
