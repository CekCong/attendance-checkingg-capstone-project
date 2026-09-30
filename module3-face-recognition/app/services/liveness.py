import mediapipe as mp
import numpy as np
from fastapi import HTTPException

from app.schemas.liveness import LivenessRequest, LivenessResponse
from app.services.arc_face import extract_face_embedding
from app.services.face_quality import calculate_quality_score
from app.services.image_decoder import decode_base64_image
from app.services.face_detector import detect_face
from app.services.sim_hash import SIMHASH_BITS, generate_face_hash
from app.services.similarity import hamming_distance

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
HEAD_CENTER_RATIO_THRESHOLD = 0.10
FACE_SIMILARITY_THRESHOLD = 0.40
REFERENCE_MATCH_THRESHOLD = 0.70
ACTIVE_FRAME_COUNT = 15
SMILE_INCREASE_RATIO = 1.08
MOUTH_LEFT_INDEX = 61
MOUTH_RIGHT_INDEX = 291

LIVENESS_THRESHOLD = 0.60
DEPTH_WEIGHT = 0.30
MESH_WEIGHT = 0.25
TEXTURE_WEIGHT = 0.25
COLOR_WEIGHT = 0.20
MIN_DEPTH = 0.01
TARGET_TEXTURE_CONTRAST = 45.0
TARGET_TEXTURE_EDGE_STRENGTH = 18.0
TARGET_COLOR_VARIATION = 45.0


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


def face_crop(image, face):
    height, width = image.shape[:2]
    bbox = face["bounding_box"]
    x_start = max(0, int(bbox["x_min"] * width))
    y_start = max(0, int(bbox["y_min"] * height))
    x_end = min(width, int((bbox["x_min"] + bbox["width"]) * width))
    y_end = min(height, int((bbox["y_min"] + bbox["height"]) * height))
    if x_end <= x_start or y_end <= y_start:
        return image
    return image[y_start:y_end, x_start:x_end]


def texture_score(image, face):
    crop = face_crop(image, face).astype(np.float32)
    if crop.size == 0:
        return 0.0

    grayscale = (
        crop[:, :, 0] * 0.299
        + crop[:, :, 1] * 0.587
        + crop[:, :, 2] * 0.114
    )
    contrast = float(np.std(grayscale))
    horizontal_edges = float(np.mean(np.abs(np.diff(grayscale, axis=1))))
    vertical_edges = float(np.mean(np.abs(np.diff(grayscale, axis=0))))
    edge_strength = (horizontal_edges + vertical_edges) / 2.0

    contrast_score = min(contrast / TARGET_TEXTURE_CONTRAST, 1.0)
    edge_score = min(edge_strength / TARGET_TEXTURE_EDGE_STRENGTH, 1.0)
    return round((contrast_score + edge_score) / 2.0, 4)


def color_distribution_score(image, face):
    crop = face_crop(image, face).astype(np.float32)
    if crop.size == 0:
        return 0.0

    channel_variation = float(np.mean(np.std(crop, axis=(0, 1))))
    return round(min(channel_variation / TARGET_COLOR_VARIATION, 1.0), 4)


def depth_score(mesh_result):
    nose_tip_z = mesh_result.get("nose_tip_z")
    if nose_tip_z is None:
        return 0.0

    depth = abs(float(nose_tip_z))
    score = (depth - MIN_DEPTH) / (GOOD_DEPTH_THRESHOLD - MIN_DEPTH)
    return round(max(0.0, min(score, 1.0)), 4)


def passive_liveness_check(request: LivenessRequest):

    # 1. Decode base64 image to numpy array
    try:
        image = decode_base64_image(request.challenge_response)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid Base64 image.")

    # 2. Detect face using MediaPipe FaceDetection
    try:
        face = detect_face(image)
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Face detection failed.") from exc

    # 3. If no face detected, return with liveness_passed=False
    if not face:
        return LivenessResponse(
            liveness_passed=False,
            liveness_score=0.0,
            liveness_threshold=LIVENESS_THRESHOLD,
            face_embedding_hash="",
            details={"error": "No face detected or multiple faces detected."}
        )
    # 4. Analyze face for liveness signals:
    confidence_score = float(face["confidence"])  # Confidence score from face detection
    image_quality_score = calculate_quality_score(image, face)

    # Keep landmark objects internal because they are not JSON serializable.
    try:
        mesh_result = analyze_face_mesh(image)
    except Exception:
        mesh_result = {
            "face_mesh_complete": False,
            "landmark_count": 0,
            "nose_tip_z": None,
            "depth_quality": "poor",
            "landmarks": None,
        }
    landmarks = mesh_result.pop("landmarks", None)
    passive_depth_score = depth_score(mesh_result)
    mesh_completeness_score = min(
        mesh_result["landmark_count"] / EXPECTED_LANDMARK_COUNT,
        1.0,
    )
    passive_texture_score = texture_score(image, face)
    passive_color_score = color_distribution_score(image, face)

    # 5. Calculate liveness_score (0.0 to 1.0)
    liveness_score = (
        passive_depth_score * DEPTH_WEIGHT
        + mesh_completeness_score * MESH_WEIGHT
        + passive_texture_score * TEXTURE_WEIGHT
        + passive_color_score * COLOR_WEIGHT
    )
    liveness_score = round(max(0.0, min(liveness_score, 1.0)), 4)

    # 6. liveness_passed = (liveness_score >= 0.60)
    liveness_passed = liveness_score >= LIVENESS_THRESHOLD

    # 7. Generate face embedding hash
    face_embedding = extract_face_embedding(image, face)

    if face_embedding is None:
        return LivenessResponse(
            liveness_passed=False,
            liveness_score=liveness_score,
            liveness_threshold=LIVENESS_THRESHOLD,
            face_embedding_hash="",
            details={"error": "Failed to extract face embedding."}
        )

    face_embedding_hash = generate_face_hash(face_embedding)

    return LivenessResponse(
        liveness_passed=liveness_passed,
        liveness_score=liveness_score,
        liveness_threshold=LIVENESS_THRESHOLD,
        face_embedding_hash=face_embedding_hash,
        details={
            "confidence_score": confidence_score,
            "image_quality_score": image_quality_score,
            "challenge_type": request.challenge_type,
            "depth_score": passive_depth_score,
            "mesh_completeness_score": round(mesh_completeness_score, 4),
            "texture_score": passive_texture_score,
            "color_distribution_score": passive_color_score,
            **mesh_result
        }
    )



def active_frame_data(frames):
    if len(frames) != ACTIVE_FRAME_COUNT:
        raise HTTPException(
            status_code=400,
            detail=f"Active liveness requires exactly {ACTIVE_FRAME_COUNT} frames.",
        )

    embeddings = []
    landmarks_per_frame = []

    for frame in frames:
        try:
            image = decode_base64_image(frame)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid Base64 frame.") from exc

        try:
            face = detect_face(image)
        except Exception as exc:
            raise HTTPException(status_code=500, detail="Face detection failed.") from exc

        if not face:
            return None, None, "Every frame must contain exactly one face."

        mesh_result = analyze_face_mesh(image)
        landmarks = mesh_result["landmarks"]
        if landmarks is None:
            return None, None, "Every frame must contain visible face landmarks."

        embedding = extract_face_embedding(image, face)
        if embedding is None:
            return None, None, "A face embedding could not be extracted from every frame."

        embeddings.append(embedding)
        landmarks_per_frame.append(landmarks)

    return embeddings, landmarks_per_frame, None


def same_person(embeddings):
    reference = embeddings[0]
    similarities = [
        float(np.dot(reference, embedding))
        for embedding in embeddings[1:]
    ]
    return all(score >= FACE_SIMILARITY_THRESHOLD for score in similarities), similarities


def matches_reference(embeddings, reference_template_hash):
    if not reference_template_hash:
        return False, [], "Active liveness requires reference_template_hash."

    match_scores = []
    try:
        for embedding in embeddings:
            current_hash = generate_face_hash(embedding)
            distance = hamming_distance(current_hash, reference_template_hash)
            match_scores.append(1.0 - (distance / SIMHASH_BITS))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid reference template hash.") from exc

    all_frames_match = all(
        score >= REFERENCE_MATCH_THRESHOLD
        for score in match_scores
    )
    error = None if all_frames_match else "Not every frame matches the enrolled face."
    return all_frames_match, match_scores, error


def contains_sequence(states, expected):
    transitions = []
    for state in states:
        if not transitions or transitions[-1] != state:
            transitions.append(state)

    size = len(expected)
    return any(
        transitions[index:index + size] == expected
        for index in range(len(transitions) - size + 1)
    )


def active_response(
    challenge_type,
    action_detected,
    same_person,
    correct_person,
    embeddings,
    similarities,
    reference_match_scores,
    details=None,
    error=None,
):
    passed = same_person and correct_person and action_detected
    response_details = {
        "challenge_type": challenge_type,
        "same_person_across_frames": same_person,
        "all_frames_match_reference": correct_person,
        "action_detected": action_detected,
    }
    if similarities is not None:
        response_details["face_similarity_scores"] = [round(score, 4) for score in similarities]
    if reference_match_scores is not None:
        response_details["reference_match_scores"] = [
            round(score, 4)
            for score in reference_match_scores
        ]
    if details:
        response_details.update(details)
    if error:
        response_details["error"] = error

    face_hash = generate_face_hash(embeddings[0]) if embeddings else ""
    return LivenessResponse(
        liveness_passed=passed,
        liveness_score=1.0 if passed else 0.0,
        liveness_threshold=LIVENESS_THRESHOLD,
        face_embedding_hash=face_hash,
        details=response_details,
    )


def prepare_active_check(request):
    embeddings, landmarks_per_frame, error = active_frame_data(request.challenge_response)
    if error:
        return None, None, None, None, False, False, error

    frames_match, similarities = same_person(embeddings)
    if not frames_match:
        return (
            embeddings,
            landmarks_per_frame,
            similarities,
            None,
            False,
            False,
            "Faces do not match across all frames.",
        )

    correct_person, reference_match_scores, error = matches_reference(
        embeddings,
        request.reference_template_hash,
    )
    if error:
        return (
            embeddings,
            landmarks_per_frame,
            similarities,
            reference_match_scores,
            True,
            False,
            error,
        )

    return embeddings, landmarks_per_frame, similarities, reference_match_scores, True, True, None


def blink_liveness_check(request):
    (
        embeddings,
        landmarks_per_frame,
        similarities,
        reference_match_scores,
        frames_match,
        correct_person,
        error,
    ) = prepare_active_check(request)
    if error:
        return active_response(
            "blink",
            False,
            frames_match,
            correct_person,
            embeddings,
            similarities,
            reference_match_scores,
            error=error,
        )

    eye_states = []
    ear_values = []
    for landmarks in landmarks_per_frame:
        left_ear = calculate_ear(landmarks, LEFT_EYE_INDICES)
        right_ear = calculate_ear(landmarks, RIGHT_EYE_INDICES)
        average_ear = (left_ear + right_ear) / 2.0
        ear_values.append(round(average_ear, 4))
        eye_states.append(average_ear >= EAR_THRESHOLD)

    blink_detected = contains_sequence(eye_states, [True, False, True])
    return active_response(
        "blink",
        blink_detected,
        frames_match,
        correct_person,
        embeddings,
        similarities,
        reference_match_scores,
        {"blink_detected": blink_detected, "eye_states": eye_states, "ear_values": ear_values},
    )


def head_turn_ratio(landmarks):
    left_x = float(landmarks[LEFT_FACE_EDGE_INDEX].x)
    right_x = float(landmarks[RIGHT_FACE_EDGE_INDEX].x)
    half_width = abs(right_x - left_x) / 2.0
    if half_width == 0:
        return 0.0
    center_x = (left_x + right_x) / 2.0
    return (float(landmarks[NOSE_TIP_INDEX].x) - center_x) / half_width


def head_turn_liveness_check(request):
    (
        embeddings,
        landmarks_per_frame,
        similarities,
        reference_match_scores,
        frames_match,
        correct_person,
        error,
    ) = prepare_active_check(request)
    if error:
        return active_response(
            "head_turn",
            False,
            frames_match,
            correct_person,
            embeddings,
            similarities,
            reference_match_scores,
            error=error,
        )

    turn_ratios = [head_turn_ratio(landmarks) for landmarks in landmarks_per_frame]
    starts_centered = abs(turn_ratios[0]) <= HEAD_CENTER_RATIO_THRESHOLD
    ends_centered = abs(turn_ratios[-1]) <= HEAD_CENTER_RATIO_THRESHOLD
    turned_between = any(
        abs(ratio) >= HEAD_TURN_RATIO_THRESHOLD
        for ratio in turn_ratios[1:-1]
    )
    head_turn_detected = starts_centered and turned_between and ends_centered

    return active_response(
        "head_turn",
        head_turn_detected,
        frames_match,
        correct_person,
        embeddings,
        similarities,
        reference_match_scores,
        {
            "head_turn_detected": head_turn_detected,
            "head_turn_ratios": [round(ratio, 4) for ratio in turn_ratios],
        },
    )

def smile_ratio(landmarks):
    mouth_left = landmarks[MOUTH_LEFT_INDEX]
    mouth_right = landmarks[MOUTH_RIGHT_INDEX]
    face_left = landmarks[LEFT_FACE_EDGE_INDEX]
    face_right = landmarks[RIGHT_FACE_EDGE_INDEX]
    mouth_width = abs(float(mouth_right.x) - float(mouth_left.x))
    face_width = abs(float(face_right.x) - float(face_left.x))
    return mouth_width / face_width if face_width else 0.0


def smile_liveness_check(request):
    (
        embeddings,
        landmarks_per_frame,
        similarities,
        reference_match_scores,
        frames_match,
        correct_person,
        error,
    ) = prepare_active_check(request)
    if error:
        return active_response(
            "smile",
            False,
            frames_match,
            correct_person,
            embeddings,
            similarities,
            reference_match_scores,
            error=error,
        )

    smile_ratios = [smile_ratio(landmarks) for landmarks in landmarks_per_frame]
    neutral_ratio = (smile_ratios[0] + smile_ratios[-1]) / 2.0
    smiled_between = any(
        ratio >= neutral_ratio * SMILE_INCREASE_RATIO
        for ratio in smile_ratios[1:-1]
    )
    returned_to_neutral = abs(smile_ratios[-1] - smile_ratios[0]) <= smile_ratios[0] * 0.10
    smile_detected = neutral_ratio > 0 and smiled_between and returned_to_neutral

    return active_response(
        "smile",
        smile_detected,
        frames_match,
        correct_person,
        embeddings,
        similarities,
        reference_match_scores,
        {
            "smile_detected": smile_detected,
            "smile_ratios": [round(ratio, 4) for ratio in smile_ratios],
        },
    )

