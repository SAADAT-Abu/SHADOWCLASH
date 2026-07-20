"""Exponential-moving-average smoothing over MediaPipe landmarks.

Landmarks arrive as an (N, 4) float array: x, y, z (normalized) + visibility.
Low-visibility joints hold their last known-good position so occlusion does
not produce jitter spikes that read as fake strikes. Joints reappearing
after a long occlusion snap to the new position instead of lerping in.
"""

import numpy as np

NUM_LANDMARKS = 33


class LandmarkSmoother:
    def __init__(
        self,
        alpha: float = 0.4,
        min_visibility: float = 0.5,
        num_landmarks: int = NUM_LANDMARKS,
    ):
        self.alpha = alpha
        self.min_visibility = min_visibility
        self.num_landmarks = num_landmarks
        self._smoothed: np.ndarray | None = None

    def reset(self) -> None:
        self._smoothed = None

    def update(self, landmarks: np.ndarray) -> np.ndarray:
        """Smooth a new (N, 4) landmark frame and return the smoothed copy."""
        landmarks = np.asarray(landmarks, dtype=np.float64)
        if landmarks.shape != (self.num_landmarks, 4):
            raise ValueError(
                f"expected shape ({self.num_landmarks}, 4), got {landmarks.shape}"
            )

        if self._smoothed is None:
            self._smoothed = landmarks.copy()
            return self._smoothed.copy()

        ema = self.alpha * landmarks + (1.0 - self.alpha) * self._smoothed
        # Joints that dropped below the visibility floor keep their previous
        # position; only their visibility value tracks the new reading.
        occluded = landmarks[:, 3] < self.min_visibility
        ema[occluded, :3] = self._smoothed[occluded, :3]
        # Joints whose held position has gone stale (smoothed visibility
        # decayed below the floor) snap to the fresh reading on reappearance
        # rather than lerping in from wherever they were lost.
        reappeared = (self._smoothed[:, 3] < self.min_visibility) & ~occluded
        ema[reappeared, :3] = landmarks[reappeared, :3]
        self._smoothed = ema
        return self._smoothed.copy()
