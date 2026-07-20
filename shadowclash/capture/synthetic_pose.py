"""Synthetic animated fighter: generates poses like a real tracked player.

API-compatible with PoseCapture (start/stop/get_pose/capture_fps), so it can
drive the VS villains and bot clients for multiplayer testing. Poses are in
camera space, exactly like MediaPipe output: the figure sways, guards, and
attacks toward +x (which faces the opponent once the peer/opponent flip is
applied).

Move-set (weighted per villain via `move_weights`):
  jab          — straight punch to head or torso
  slap         — arcing open-hand strike; when hand visuals are enabled the
                 21-landmark hand rows are filled so real fingers render
  kick         — front kick with the right leg
  flying_kick  — jumping kick: whole body lifts, leg extends high and far
  somersault   — full-body flip: the figure rotates 360° while airborne;
                 spinning limbs strike anything in reach
"""

import math
import time

import numpy as np

from shadowclash.skeleton import skeleton_model as sm

DEFAULT_WEIGHTS = {"jab": 0.55, "slap": 0.2, "kick": 0.25}

# Open-hand template in hand-local coords (+x = strike direction, unit hand
# length), matching MediaPipe's 21-landmark topology: wrist, thumb chain,
# index/middle/ring/pinky chains.
HAND_TEMPLATE = np.array(
    [
        (0.0, 0.0),
        (0.15, -0.25), (0.30, -0.35), (0.45, -0.40), (0.55, -0.42),   # thumb
        (0.45, -0.15), (0.65, -0.17), (0.80, -0.18), (0.92, -0.19),   # index
        (0.45, 0.00), (0.68, 0.00), (0.85, 0.00), (1.00, 0.00),       # middle
        (0.44, 0.14), (0.65, 0.15), (0.80, 0.16), (0.92, 0.17),       # ring
        (0.40, 0.28), (0.55, 0.30), (0.68, 0.32), (0.78, 0.34),       # pinky
    ]
)


class SyntheticPoseDriver:
    def __init__(
        self,
        config: dict | None = None,
        seed: int | None = None,
        attack_interval: tuple[float, float] = (0.8, 2.0),
        attack_duration: float = 0.42,
        kick_prob: float | None = None,
        reach: float = 0.30,
        move_weights: dict[str, float] | None = None,
    ):
        self._rng = np.random.default_rng(seed)
        self._t0 = time.monotonic()
        # Active move: (move, limb, start_time, duration, zone)
        self._attack: tuple[str, str | None, float, float, str] | None = None
        self._next_attack = 1.2
        self.capture_fps = 60.0
        # Difficulty knobs: shorter intervals = more attacks; shorter duration
        # = faster strikes = more damage (damage scales with limb velocity)
        self.attack_interval = attack_interval
        self.attack_duration = attack_duration
        self.reach = reach
        if move_weights is None:
            kick = 0.25 if kick_prob is None else kick_prob
            move_weights = {"jab": max(0.05, 0.8 - kick), "slap": 0.2, "kick": kick}
        total = sum(move_weights.values())
        self._moves = list(move_weights)
        self._weights = [w / total for w in move_weights.values()]
        # Fill real finger landmarks during slaps when hand tracking is shown
        self.hand_visuals = bool(config and config.get("pose", {}).get("hand_tracking"))
        # When False the fighter stops throwing strikes (post-KO idle)
        self.fighting = True

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def get_pose(self) -> tuple[np.ndarray, float]:
        now = time.monotonic()
        return self.pose_at(now - self._t0), now

    def get_frame(self):
        return None

    # ------------------------------------------------------------------
    def _move_duration(self, move: str) -> float:
        if move == "flying_kick":
            return self.attack_duration * 1.6
        if move == "somersault":
            return max(self.attack_duration * 2.2, 0.7)
        return self.attack_duration

    def pose_at(self, t: float) -> np.ndarray:
        """Deterministic-in-shape pose at time t (seconds since start)."""
        if not self.fighting:
            self._attack = None
            self._next_attack = t + 1.0
        elif self._attack is None and t >= self._next_attack:
            move = str(self._rng.choice(self._moves, p=self._weights))
            if move in ("jab", "slap"):
                limb = str(self._rng.choice(["right_fist", "left_fist"]))
            elif move in ("kick", "flying_kick"):
                limb = "right_foot"
            else:
                limb = None
            zone = "head" if move == "flying_kick" else str(self._rng.choice(["head", "torso", "torso"]))
            self._attack = (move, limb, t, self._move_duration(move), zone)
        if self._attack is not None and t >= self._attack[2] + self._attack[3]:
            self._attack = None
            self._next_attack = t + float(self._rng.uniform(*self.attack_interval))

        cx = 0.42 + 0.06 * math.sin(t * 0.6)
        bob = 0.008 * math.sin(t * 3.4)
        sway = 0.01 * math.sin(t * 1.7)

        pose = np.zeros((sm.TOTAL_LANDMARKS, 4))
        pose[: sm.NUM_POSE_LANDMARKS, 3] = 1.0

        def put(idx: int, x: float, y: float) -> None:
            pose[idx, 0] = x + sway
            pose[idx, 1] = y + bob

        put(sm.NOSE, cx, 0.22)
        put(sm.LEFT_EAR, cx - 0.03, 0.23)
        put(sm.RIGHT_EAR, cx + 0.03, 0.23)
        put(sm.LEFT_SHOULDER, cx - 0.06, 0.35)
        put(sm.RIGHT_SHOULDER, cx + 0.06, 0.35)
        put(sm.LEFT_HIP, cx - 0.05, 0.55)
        put(sm.RIGHT_HIP, cx + 0.05, 0.55)
        put(sm.LEFT_KNEE, cx - 0.05, 0.72)
        put(sm.RIGHT_KNEE, cx + 0.05, 0.72)
        put(sm.LEFT_ANKLE, cx - 0.05, 0.88)
        put(sm.RIGHT_ANKLE, cx + 0.05, 0.88)
        put(sm.LEFT_HEEL, cx - 0.06, 0.90)
        put(sm.RIGHT_HEEL, cx + 0.04, 0.90)
        put(sm.LEFT_FOOT_INDEX, cx - 0.03, 0.91)
        put(sm.RIGHT_FOOT_INDEX, cx + 0.07, 0.91)

        # Guard stance: elbows tucked, fists near the chin
        put(sm.LEFT_ELBOW, cx - 0.09, 0.45)
        put(sm.RIGHT_ELBOW, cx + 0.09, 0.45)
        put(sm.LEFT_WRIST, cx - 0.045, 0.31)
        put(sm.RIGHT_WRIST, cx + 0.045, 0.31)
        # Stylized-hand knuckles trail slightly outward from each wrist
        put(sm.LEFT_THUMB, cx - 0.055, 0.29)
        put(sm.LEFT_INDEX, cx - 0.06, 0.30)
        put(sm.LEFT_PINKY, cx - 0.05, 0.32)
        put(sm.RIGHT_THUMB, cx + 0.055, 0.29)
        put(sm.RIGHT_INDEX, cx + 0.06, 0.30)
        put(sm.RIGHT_PINKY, cx + 0.05, 0.32)

        if self._attack is not None:
            move, limb, start, dur, zone = self._attack
            phase = min(max((t - start) / dur, 0.0), 1.0)
            # Fast extension, slower retraction
            amp = math.sin(math.pi * phase) ** 0.8

            if move in ("jab", "slap"):
                target_y = 0.24 if zone == "head" else 0.44
                wrist = sm.RIGHT_WRIST if limb == "right_fist" else sm.LEFT_WRIST
                elbow = sm.RIGHT_ELBOW if limb == "right_fist" else sm.LEFT_ELBOW
                guard = pose[wrist, :2].copy()
                target = np.array([cx + self.reach, target_y])
                pose[wrist, :2] = guard + (target - guard) * amp
                if move == "slap":
                    # Arcing swing: the hand sweeps vertically through the strike
                    pose[wrist, 1] += 0.07 * math.sin(2 * math.pi * phase)
                pose[elbow, :2] = (pose[wrist, :2] + pose[elbow, :2]) / 2.0
                knuckles = (
                    (sm.RIGHT_THUMB, sm.RIGHT_INDEX, sm.RIGHT_PINKY)
                    if limb == "right_fist"
                    else (sm.LEFT_THUMB, sm.LEFT_INDEX, sm.LEFT_PINKY)
                )
                for k in knuckles:
                    pose[k, :2] = pose[wrist, :2] + (pose[k, :2] - guard)
                if move == "slap" and self.hand_visuals:
                    self._fill_open_hand(pose, limb, amp)

            elif move == "kick":
                guard = pose[sm.RIGHT_ANKLE, :2].copy()
                target = np.array([cx + self.reach + 0.02, 0.52])
                pose[sm.RIGHT_ANKLE, :2] = guard + (target - guard) * amp
                pose[sm.RIGHT_KNEE, :2] = (pose[sm.RIGHT_ANKLE, :2] + pose[sm.RIGHT_HIP, :2]) / 2.0
                pose[sm.RIGHT_HEEL, :2] = pose[sm.RIGHT_ANKLE, :2] + [-0.01, 0.02]
                pose[sm.RIGHT_FOOT_INDEX, :2] = pose[sm.RIGHT_ANKLE, :2] + [0.03, 0.01]

            elif move == "flying_kick":
                lift = 0.12 * math.sin(math.pi * phase)
                pose[: sm.NUM_POSE_LANDMARKS, 1] -= lift
                guard = pose[sm.RIGHT_ANKLE, :2].copy()
                target = np.array([cx + self.reach + 0.10, 0.38])
                pose[sm.RIGHT_ANKLE, :2] = guard + (target - guard) * amp
                pose[sm.RIGHT_KNEE, :2] = (pose[sm.RIGHT_ANKLE, :2] + pose[sm.RIGHT_HIP, :2]) / 2.0
                pose[sm.RIGHT_HEEL, :2] = pose[sm.RIGHT_ANKLE, :2] + [-0.01, 0.02]
                pose[sm.RIGHT_FOOT_INDEX, :2] = pose[sm.RIGHT_ANKLE, :2] + [0.03, 0.0]
                # Trailing leg tucks under the body
                pose[sm.LEFT_ANKLE, :2] = (pose[sm.LEFT_ANKLE, :2] + pose[sm.LEFT_HIP, :2]) / 2.0
                pose[sm.LEFT_KNEE, :2] = (pose[sm.LEFT_ANKLE, :2] + pose[sm.LEFT_HIP, :2]) / 2.0

            elif move == "somersault":
                # Full airborne flip about the body center; spinning limbs
                # can clip the opponent at close range
                angle = 2 * math.pi * phase
                lift = 0.10 * math.sin(math.pi * phase)
                center = np.array([cx + sway, 0.55 + bob - lift])
                pose[: sm.NUM_POSE_LANDMARKS, 1] -= lift
                cos_a, sin_a = math.cos(angle), math.sin(angle)
                rel = pose[: sm.NUM_POSE_LANDMARKS, :2] - center
                pose[: sm.NUM_POSE_LANDMARKS, 0] = center[0] + rel[:, 0] * cos_a - rel[:, 1] * sin_a
                pose[: sm.NUM_POSE_LANDMARKS, 1] = center[1] + rel[:, 0] * sin_a + rel[:, 1] * cos_a

        np.clip(pose[: sm.NUM_POSE_LANDMARKS, :2], 0.0, 1.0, out=pose[: sm.NUM_POSE_LANDMARKS, :2])
        return pose

    def _fill_open_hand(self, pose: np.ndarray, limb: str, amp: float) -> None:
        """Populate the 21 Holistic hand rows with an open palm mid-slap."""
        wrist = sm.RIGHT_WRIST if limb == "right_fist" else sm.LEFT_WRIST
        start = sm.RIGHT_HAND_START if limb == "right_fist" else sm.LEFT_HAND_START
        scale = 0.09
        # Fingers point along the strike direction (+x), splaying with amp
        pts = HAND_TEMPLATE * scale
        pose[start : start + sm.HAND_LANDMARKS, 0] = pose[wrist, 0] + pts[:, 0]
        pose[start : start + sm.HAND_LANDMARKS, 1] = pose[wrist, 1] + pts[:, 1] * (0.5 + 0.5 * amp)
        pose[start : start + sm.HAND_LANDMARKS, 3] = 1.0
