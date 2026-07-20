"""Maps MediaPipe's 33 pose landmarks to game limb segments and hit zones.

All game-space coordinates are normalized arena units: x in [0, 1] left to
right, y in [0, 1] top to bottom (D-008). Strike velocities are expressed in
torso-lengths per second so thresholds are camera-framing invariant (D-005).
"""

import numpy as np

# MediaPipe PoseLandmark indices
NOSE = 0
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_ELBOW = 13
RIGHT_ELBOW = 14
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_PINKY = 17
RIGHT_PINKY = 18
LEFT_INDEX = 19
RIGHT_INDEX = 20
LEFT_THUMB = 21
RIGHT_THUMB = 22
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32

# Bone connections rendered as the stick figure
BONES = [
    (LEFT_SHOULDER, RIGHT_SHOULDER),
    (LEFT_SHOULDER, LEFT_ELBOW),
    (LEFT_ELBOW, LEFT_WRIST),
    (RIGHT_SHOULDER, RIGHT_ELBOW),
    (RIGHT_ELBOW, RIGHT_WRIST),
    (LEFT_SHOULDER, LEFT_HIP),
    (RIGHT_SHOULDER, RIGHT_HIP),
    (LEFT_HIP, RIGHT_HIP),
    (LEFT_HIP, LEFT_KNEE),
    (LEFT_KNEE, LEFT_ANKLE),
    (RIGHT_HIP, RIGHT_KNEE),
    (RIGHT_KNEE, RIGHT_ANKLE),
]

# Joints that get a rounded cap drawn over bone ends
JOINTS = [
    LEFT_SHOULDER, RIGHT_SHOULDER, LEFT_ELBOW, RIGHT_ELBOW,
    LEFT_HIP, RIGHT_HIP, LEFT_KNEE, RIGHT_KNEE,
]

# Hands: wrist + knuckle landmarks — the stylized fallback when full
# Holistic hand tracking has no detection for that hand
HANDS = {
    "left": (LEFT_WRIST, LEFT_THUMB, LEFT_INDEX, LEFT_PINKY),
    "right": (RIGHT_WRIST, RIGHT_THUMB, RIGHT_INDEX, RIGHT_PINKY),
}

# Holistic extension (D-011): rows 33-53 = left hand, 54-74 = right hand,
# each a full 21-landmark MediaPipe hand
NUM_POSE_LANDMARKS = 33
HAND_LANDMARKS = 21
LEFT_HAND_START = 33
RIGHT_HAND_START = 54
TOTAL_LANDMARKS = 75

# MediaPipe hand topology (indices within one 21-point hand)
HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),          # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),          # index
    (5, 9), (9, 10), (10, 11), (11, 12),     # middle
    (9, 13), (13, 14), (14, 15), (15, 16),   # ring
    (13, 17), (17, 18), (18, 19), (19, 20),  # pinky
    (0, 17),                                 # palm edge
]
HAND_PALM_IDX = [0, 1, 5, 9, 13, 17]


def hand_tracked(visibility: np.ndarray, start: int, min_visibility: float = 0.3) -> bool:
    """True if the Holistic hand block at `start` holds live tracked data.

    `visibility` is the (N,) visibility column of the landmark array.
    """
    return visibility.shape[0] >= TOTAL_LANDMARKS and visibility[start] >= min_visibility

# Feet: ankle + heel + toe triangle
FEET = {
    "left": (LEFT_ANKLE, LEFT_HEEL, LEFT_FOOT_INDEX),
    "right": (RIGHT_ANKLE, RIGHT_HEEL, RIGHT_FOOT_INDEX),
}

# Striking limbs: name -> landmark index
STRIKE_LIMBS = {
    "left_fist": LEFT_WRIST,
    "right_fist": RIGHT_WRIST,
    "left_foot": LEFT_ANKLE,
    "right_foot": RIGHT_ANKLE,
}

# Receiving leg segments: name -> (knee, ankle)
LEG_SEGMENTS = {
    "left_leg": (LEFT_KNEE, LEFT_ANKLE),
    "right_leg": (RIGHT_KNEE, RIGHT_ANKLE),
}

ZONE_HEAD = "head"
ZONE_TORSO = "torso"
ZONE_LEG = "leg"


def to_arena(pose: np.ndarray, flip: bool = False) -> np.ndarray:
    """Camera-normalized (33, 4) pose -> arena-space (33, 2) xy.

    flip=True mirrors horizontally, used for the peer avatar so both
    fighters face each other.
    """
    xy = pose[:, :2].copy()
    if flip:
        xy[:, 0] = 1.0 - xy[:, 0]
    return xy


def torso_length(xy: np.ndarray) -> float:
    """Mean shoulder-to-hip distance; the scale unit for velocity/radii."""
    left = np.linalg.norm(xy[LEFT_SHOULDER] - xy[LEFT_HIP])
    right = np.linalg.norm(xy[RIGHT_SHOULDER] - xy[RIGHT_HIP])
    length = (left + right) / 2.0
    return max(length, 1e-3)


def head_center(xy: np.ndarray) -> np.ndarray:
    return np.mean([xy[NOSE], xy[LEFT_EAR], xy[RIGHT_EAR]], axis=0)


def head_radius(xy: np.ndarray) -> float:
    ear_span = np.linalg.norm(xy[LEFT_EAR] - xy[RIGHT_EAR])
    return max(ear_span * 0.8, torso_length(xy) * 0.18)


def torso_endpoints(xy: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """Torso as a capsule: shoulder-center to hip-center, radius = half width."""
    top = (xy[LEFT_SHOULDER] + xy[RIGHT_SHOULDER]) / 2.0
    bottom = (xy[LEFT_HIP] + xy[RIGHT_HIP]) / 2.0
    shoulder_w = np.linalg.norm(xy[LEFT_SHOULDER] - xy[RIGHT_SHOULDER])
    return top, bottom, max(shoulder_w / 2.0, 0.02)


def strike_radius(xy: np.ndarray) -> float:
    return torso_length(xy) * 0.14


def leg_radius(xy: np.ndarray) -> float:
    return torso_length(xy) * 0.10


def is_blocking(xy: np.ndarray, strike_pos: np.ndarray) -> bool:
    """Block check: a forearm (wrist) raised above shoulder height and
    horizontally between the incoming strike and the defender's torso center.
    Note y is down, so "above" means smaller y.
    """
    torso_cx = (xy[LEFT_SHOULDER, 0] + xy[RIGHT_SHOULDER, 0] + xy[LEFT_HIP, 0] + xy[RIGHT_HIP, 0]) / 4.0
    shoulder_y = min(xy[LEFT_SHOULDER, 1], xy[RIGHT_SHOULDER, 1])
    margin = torso_length(xy) * 0.15
    for wrist in (LEFT_WRIST, RIGHT_WRIST):
        wx, wy = xy[wrist]
        if wy > shoulder_y + margin:
            continue  # forearm not raised
        lo, hi = sorted((strike_pos[0], torso_cx))
        if lo - margin <= wx <= hi + margin:
            return True
    return False
