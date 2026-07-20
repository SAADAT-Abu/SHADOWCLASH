import numpy as np
import pytest

from shadowclash.capture.landmark_smoother import LandmarkSmoother


def make_frame(value: float, visibility: float = 1.0) -> np.ndarray:
    frame = np.full((33, 4), value, dtype=np.float64)
    frame[:, 3] = visibility
    return frame


def test_first_frame_passes_through():
    smoother = LandmarkSmoother(alpha=0.4)
    frame = make_frame(0.5)
    out = smoother.update(frame)
    assert np.allclose(out, frame)


def test_ema_formula():
    smoother = LandmarkSmoother(alpha=0.4)
    smoother.update(make_frame(0.0))
    out = smoother.update(make_frame(1.0))
    # smoothed = 0.4 * 1.0 + 0.6 * 0.0
    assert np.allclose(out[:, :3], 0.4)


def test_ema_converges_toward_input():
    smoother = LandmarkSmoother(alpha=0.4)
    smoother.update(make_frame(0.0))
    out = None
    for _ in range(30):
        out = smoother.update(make_frame(1.0))
    assert np.all(out[:, :3] > 0.99)


def test_low_visibility_holds_position():
    smoother = LandmarkSmoother(alpha=0.4, min_visibility=0.5)
    smoother.update(make_frame(0.5))
    occluded = make_frame(0.9, visibility=0.2)
    out = smoother.update(occluded)
    assert np.allclose(out[:, :3], 0.5)  # position held
    assert np.allclose(out[:, 3], 0.4 * 0.2 + 0.6 * 1.0)  # visibility still tracks


def test_visibility_recovery_resumes_smoothing():
    smoother = LandmarkSmoother(alpha=0.5, min_visibility=0.5)
    smoother.update(make_frame(0.5))
    smoother.update(make_frame(0.9, visibility=0.1))
    out = smoother.update(make_frame(0.9, visibility=1.0))
    assert np.allclose(out[:, :3], 0.7)  # 0.5 * 0.9 + 0.5 * 0.5


def test_rejects_bad_shape():
    with pytest.raises(ValueError):
        LandmarkSmoother().update(np.zeros((10, 4)))


def test_custom_landmark_count():
    smoother = LandmarkSmoother(num_landmarks=75)
    out = smoother.update(np.zeros((75, 4)))
    assert out.shape == (75, 4)
    with pytest.raises(ValueError):
        smoother.update(np.zeros((33, 4)))


def test_reappearance_snaps_instead_of_lerping():
    smoother = LandmarkSmoother(alpha=0.5, min_visibility=0.5)
    smoother.update(make_frame(0.5))
    # Long occlusion: smoothed visibility decays below the floor (0.5 -> 0.25)
    smoother.update(make_frame(0.9, visibility=0.0))
    smoother.update(make_frame(0.9, visibility=0.0))
    # Reappears far away: position snaps to the fresh reading, no lerp-in
    out = smoother.update(make_frame(0.9, visibility=1.0))
    assert np.allclose(out[:, :3], 0.9)
