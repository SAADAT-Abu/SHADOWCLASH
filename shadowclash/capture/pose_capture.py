"""Threaded webcam + MediaPipe Holistic capture.

Runs camera grabbing and inference in a daemon thread so the game loop is
never blocked by the inference cost (see DECISIONS.md D-003). Frames are
mirror-flipped before inference (D-007) so the avatar moves like a mirror
image of the player.

Holistic (D-011) yields the 33 pose landmarks plus 21 real landmarks per
hand; the combined (75, 4) array uses rows 33-53 for the left hand and
54-74 for the right, with visibility 1.0 while the hand is tracked and 0.0
otherwise (the smoother holds last-known positions across dropouts).
"""

import threading
import time

import cv2
import numpy as np

from shadowclash.utils.logger import get_logger

log = get_logger(__name__)


class PoseCapture:
    def __init__(self, config: dict):
        cam = config["camera"]
        pose_cfg = config["pose"]
        self.cam_index = cam["index"]
        self.cam_width = cam["width"]
        self.cam_height = cam["height"]
        self.cam_fps = cam["fps"]
        self.min_detection_confidence = pose_cfg["min_detection_confidence"]
        self.min_tracking_confidence = pose_cfg["min_tracking_confidence"]
        self.model_complexity = pose_cfg.get("model_complexity", 0)
        self.hand_tracking = pose_cfg.get("hand_tracking", False)

        from shadowclash.capture.landmark_smoother import LandmarkSmoother
        from shadowclash.skeleton import skeleton_model as sm

        self._smoother = LandmarkSmoother(
            alpha=pose_cfg["smoothing_alpha"],
            min_visibility=pose_cfg["min_joint_visibility"],
            num_landmarks=sm.TOTAL_LANDMARKS,
        )
        self._lock = threading.Lock()
        self._latest_pose: np.ndarray | None = None
        self._latest_pose_time: float = 0.0
        self._latest_frame: np.ndarray | None = None
        self._running = False
        self._thread: threading.Thread | None = None
        self.capture_fps: float = 0.0

    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def get_pose(self) -> tuple[np.ndarray | None, float]:
        """Latest smoothed (33, 4) landmarks and their capture timestamp."""
        with self._lock:
            pose = None if self._latest_pose is None else self._latest_pose.copy()
            return pose, self._latest_pose_time

    def get_frame(self) -> np.ndarray | None:
        """Latest mirrored BGR frame (for the posecheck debug mode)."""
        with self._lock:
            return None if self._latest_frame is None else self._latest_frame.copy()

    def _capture_loop(self) -> None:
        import mediapipe as mp

        from shadowclash.skeleton import skeleton_model as sm

        cap = cv2.VideoCapture(self.cam_index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.cam_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.cam_height)
        cap.set(cv2.CAP_PROP_FPS, self.cam_fps)
        if not cap.isOpened():
            log.error("Cannot open webcam index %s", self.cam_index)
            self._running = False
            return

        # Holistic (real fingers) or plain Pose (stylized hands, faster) —
        # both fill the same (75, 4) array; Pose leaves hand rows at
        # visibility 0 so the renderer falls back to stylized hands.
        if self.hand_tracking:
            model = mp.solutions.holistic.Holistic(
                model_complexity=self.model_complexity,
                min_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
            )
        else:
            model = mp.solutions.pose.Pose(
                model_complexity=self.model_complexity,
                min_detection_confidence=self.min_detection_confidence,
                min_tracking_confidence=self.min_tracking_confidence,
            )
        log.info(
            "%s capture started on camera %s (model complexity %s)",
            "Holistic" if self.hand_tracking else "Pose",
            self.cam_index,
            self.model_complexity,
        )
        last_frame_time = time.monotonic()
        try:
            while self._running:
                ok, frame = cap.read()
                if not ok:
                    time.sleep(0.05)
                    continue
                now = time.monotonic()
                frame_dt = now - last_frame_time
                last_frame_time = now
                if frame_dt > 0:
                    self.capture_fps = 0.9 * self.capture_fps + 0.1 / frame_dt
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = model.process(rgb)

                landmarks = None
                if result.pose_landmarks is not None:
                    landmarks = np.zeros((sm.TOTAL_LANDMARKS, 4), dtype=np.float64)
                    landmarks[: sm.NUM_POSE_LANDMARKS] = [
                        (lm.x, lm.y, lm.z, lm.visibility)
                        for lm in result.pose_landmarks.landmark
                    ]
                    for hand_result, start in (
                        (getattr(result, "left_hand_landmarks", None), sm.LEFT_HAND_START),
                        (getattr(result, "right_hand_landmarks", None), sm.RIGHT_HAND_START),
                    ):
                        if hand_result is not None:
                            landmarks[start : start + sm.HAND_LANDMARKS] = [
                                (lm.x, lm.y, lm.z, 1.0) for lm in hand_result.landmark
                            ]
                    landmarks = self._smoother.update(landmarks)

                with self._lock:
                    self._latest_frame = frame
                    if landmarks is not None:
                        self._latest_pose = landmarks
                        self._latest_pose_time = time.monotonic()
        finally:
            model.close()
            cap.release()
            log.info("Capture stopped")


def run_posecheck(config: dict) -> None:
    """M1 sanity check: live webcam window with the skeleton drawn on top."""
    import mediapipe as mp

    from shadowclash.skeleton import skeleton_model as sm

    capture = PoseCapture(config)
    capture.start()
    connections = mp.solutions.pose.POSE_CONNECTIONS
    log.info("Posecheck running - press Q or Esc to quit")
    try:
        while True:
            frame = capture.get_frame()
            pose, _ = capture.get_pose()
            if frame is not None:
                h, w = frame.shape[:2]
                if pose is not None:
                    for a, b in connections:
                        pa = (int(pose[a, 0] * w), int(pose[a, 1] * h))
                        pb = (int(pose[b, 0] * w), int(pose[b, 1] * h))
                        cv2.line(frame, pa, pb, (0, 255, 0), 2)
                    for start in (sm.LEFT_HAND_START, sm.RIGHT_HAND_START):
                        if not sm.hand_tracked(pose[:, 3], start):
                            continue
                        for a, b in sm.HAND_CONNECTIONS:
                            pa = pose[start + a]
                            pb = pose[start + b]
                            cv2.line(
                                frame,
                                (int(pa[0] * w), int(pa[1] * h)),
                                (int(pb[0] * w), int(pb[1] * h)),
                                (255, 200, 0),
                                2,
                            )
                    for x, y, _, vis in pose:
                        if vis >= 0.5:
                            cv2.circle(frame, (int(x * w), int(y * h)), 3, (0, 128, 255), -1)
                cv2.imshow("SHADOWCLASH posecheck (Q to quit)", frame)
            key = cv2.waitKey(15) & 0xFF
            if key in (ord("q"), 27):
                break
    finally:
        capture.stop()
        cv2.destroyAllWindows()
