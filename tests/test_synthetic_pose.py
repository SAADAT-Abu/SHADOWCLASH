import numpy as np

from shadowclash.capture.synthetic_pose import SyntheticPoseDriver
from shadowclash.skeleton import skeleton_model as sm


def test_pose_shape_and_visibility():
    driver = SyntheticPoseDriver(seed=1)
    pose = driver.pose_at(0.0)
    assert pose.shape == (sm.TOTAL_LANDMARKS, 4)
    assert np.all(pose[: sm.NUM_POSE_LANDMARKS, 3] == 1.0)
    assert np.all(pose[sm.LEFT_HAND_START :, 3] == 0.0)  # stylized hands


def test_torso_length_is_plausible():
    driver = SyntheticPoseDriver(seed=1)
    for t in np.linspace(0, 10, 50):
        torso = sm.torso_length(driver.pose_at(float(t))[:, :2])
        assert 0.15 < torso < 0.25


def test_bot_throws_strikes_above_threshold():
    """Sampled at 30fps over 10s, some limb must exceed the hit threshold."""
    driver = SyntheticPoseDriver(seed=2)
    dt = 1.0 / 30.0
    max_velocity = 0.0
    prev = None
    for i in range(300):
        pose = driver.pose_at(i * dt)
        xy = pose[:, :2]
        if prev is not None:
            for idx in sm.STRIKE_LIMBS.values():
                v = np.linalg.norm(xy[idx] - prev[idx]) / dt / sm.torso_length(xy)
                max_velocity = max(max_velocity, v)
        prev = xy
    assert max_velocity > 3.0  # exceeds min_strike_velocity


def max_strike_velocity(driver: SyntheticPoseDriver, seconds: float = 10.0) -> float:
    dt = 1.0 / 30.0
    fastest = 0.0
    prev = None
    for i in range(int(seconds / dt)):
        xy = driver.pose_at(i * dt)[:, :2]
        if prev is not None:
            for idx in sm.STRIKE_LIMBS.values():
                v = np.linalg.norm(xy[idx] - prev[idx]) / dt / sm.torso_length(xy)
                fastest = max(fastest, v)
        prev = xy
    return fastest


def test_fighting_flag_stops_attacks():
    driver = SyntheticPoseDriver(seed=4)
    driver.fighting = False
    # Idle sway/bob only — never approaches the strike threshold
    assert max_strike_velocity(driver) < 3.0


def test_difficulty_scales_attack_frequency():
    def strike_frames(params: dict) -> int:
        driver = SyntheticPoseDriver(seed=5, **params)
        dt = 1.0 / 30.0
        count = 0
        prev = None
        for i in range(600):
            xy = driver.pose_at(i * dt)[:, :2]
            if prev is not None:
                for idx in sm.STRIKE_LIMBS.values():
                    if np.linalg.norm(xy[idx] - prev[idx]) / dt / sm.torso_length(xy) > 3.0:
                        count += 1
                        break
            prev = xy
        return count

    easy = strike_frames(dict(attack_interval=(2.0, 3.0), attack_duration=0.55))
    hard = strike_frames(dict(attack_interval=(0.4, 0.7), attack_duration=0.26))
    assert hard > easy * 1.5


def test_bot_stays_in_frame():
    driver = SyntheticPoseDriver(seed=3)
    for t in np.linspace(0, 20, 100):
        pose = driver.pose_at(float(t))
        body = pose[: sm.NUM_POSE_LANDMARKS, :2]
        assert np.all(body >= 0.0) and np.all(body <= 1.0)


def test_new_moves_stay_in_frame_and_strike():
    """Flying kicks and somersaults keep the body in bounds and land fast strikes."""
    driver = SyntheticPoseDriver(
        seed=6,
        attack_interval=(0.4, 0.7),
        attack_duration=0.30,
        move_weights={"flying_kick": 0.5, "somersault": 0.5},
    )
    dt = 1.0 / 30.0
    fastest = 0.0
    prev = None
    for i in range(600):
        pose = driver.pose_at(i * dt)
        body = pose[: sm.NUM_POSE_LANDMARKS, :2]
        assert np.all(body >= 0.0) and np.all(body <= 1.0)
        if prev is not None:
            for idx in sm.STRIKE_LIMBS.values():
                v = np.linalg.norm(body[idx] - prev[idx]) / dt / sm.torso_length(body)
                fastest = max(fastest, v)
        prev = body
    assert fastest > 3.0


def test_slap_fills_hand_rows_when_hand_visuals_on():
    config = {"pose": {"hand_tracking": True}}
    driver = SyntheticPoseDriver(
        config, seed=7, attack_interval=(0.1, 0.2), move_weights={"slap": 1.0}
    )
    saw_hand = False
    for i in range(300):
        pose = driver.pose_at(i / 30.0)
        if pose[sm.LEFT_HAND_START :, 3].any():
            saw_hand = True
            break
    assert saw_hand
    # With visuals off, hand rows always stay empty
    driver_off = SyntheticPoseDriver(
        seed=7, attack_interval=(0.1, 0.2), move_weights={"slap": 1.0}
    )
    for i in range(300):
        assert not driver_off.pose_at(i / 30.0)[sm.LEFT_HAND_START :, 3].any()


def test_joined_hands_guard_blocks():
    from tests.test_collision_engine import make_pose

    guard = make_pose()[:, :2]
    # Join both wrists in front of the chest (Tekken guard)
    guard[sm.LEFT_WRIST] = (0.49, 0.40)
    guard[sm.RIGHT_WRIST] = (0.51, 0.40)
    assert sm.is_guarding(guard)
    assert sm.is_blocking(guard, np.array([0.7, 0.35]))
    # Hands apart at the waist: no guard
    idle = make_pose()[:, :2]
    assert not sm.is_guarding(idle)


def test_distance_hint_thresholds():
    from shadowclash.modes.singleplayer_vs import distance_hint

    assert distance_hint(0.5, 1.0) == "step CLOSER to the camera"
    assert distance_hint(1.0, 1.0) is None
    assert distance_hint(1.5, 1.0) == "step BACK from the camera"
