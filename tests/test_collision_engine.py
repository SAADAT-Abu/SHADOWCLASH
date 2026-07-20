import numpy as np

from shadowclash.physics.collision_engine import CollisionEngine, CooldownRegistry
from shadowclash.physics.damage_system import DamageSystem
from shadowclash.physics.hitbox_manager import FighterHitboxes, PoleHitboxes
from shadowclash.skeleton import skeleton_model as sm
from tests.test_damage_system import CONFIG

DT = 1.0 / 30.0


def make_pose(cx: float = 0.5, right_wrist: tuple[float, float] | None = None) -> np.ndarray:
    """Synthetic standing pose centered at cx; torso length ~0.2 arena units."""
    pose = np.zeros((33, 4))
    pose[:, 3] = 1.0
    points = {
        sm.NOSE: (cx, 0.22),
        sm.LEFT_EAR: (cx - 0.03, 0.23),
        sm.RIGHT_EAR: (cx + 0.03, 0.23),
        sm.LEFT_SHOULDER: (cx - 0.06, 0.35),
        sm.RIGHT_SHOULDER: (cx + 0.06, 0.35),
        sm.LEFT_ELBOW: (cx - 0.10, 0.45),
        sm.RIGHT_ELBOW: (cx + 0.10, 0.45),
        sm.LEFT_WRIST: (cx - 0.12, 0.52),
        sm.RIGHT_WRIST: right_wrist or (cx + 0.12, 0.52),
        sm.LEFT_HIP: (cx - 0.05, 0.55),
        sm.RIGHT_HIP: (cx + 0.05, 0.55),
        sm.LEFT_KNEE: (cx - 0.05, 0.72),
        sm.RIGHT_KNEE: (cx + 0.05, 0.72),
        sm.LEFT_ANKLE: (cx - 0.05, 0.88),
        sm.RIGHT_ANKLE: (cx + 0.05, 0.88),
    }
    for idx, (x, y) in points.items():
        pose[idx, 0], pose[idx, 1] = x, y
    return pose


def make_engine() -> tuple[CollisionEngine, FighterHitboxes]:
    engine = CollisionEngine(CONFIG, DamageSystem(CONFIG))
    fighter = FighterHitboxes(engine.space, "A")
    PoleHitboxes(engine.space, "B")
    return engine, fighter


def punch_pole(engine, fighter, now_ms):
    """Move the right fist quickly into the pole's torso zone."""
    fighter.update(make_pose(right_wrist=(0.58, 0.48))[:, :2], DT)
    fighter.update(make_pose(right_wrist=(0.72, 0.48))[:, :2], DT)
    return engine.check_strikes(fighter, "B", now_ms)


def test_cooldown_registry():
    reg = CooldownRegistry(600)
    assert reg.ready(("a", "b"), 1000.0)
    assert not reg.ready(("a", "b"), 1300.0)  # within cooldown
    assert reg.ready(("other", "b"), 1300.0)  # different pair unaffected
    assert reg.ready(("a", "b"), 1601.0)  # cooldown expired


def test_fast_punch_registers_hit():
    engine, fighter = make_engine()
    hits = punch_pole(engine, fighter, now_ms=0.0)
    assert len(hits) == 1
    assert hits[0].zone == sm.ZONE_TORSO
    assert hits[0].defender == "B"
    assert engine.damage.hp["B"] < 100


def test_slow_touch_does_not_register():
    engine, fighter = make_engine()
    # Wrist creeps into the zone at ~0.3 torso-lengths/sec, under threshold 3.0
    fighter.update(make_pose(right_wrist=(0.718, 0.48))[:, :2], DT)
    fighter.update(make_pose(right_wrist=(0.720, 0.48))[:, :2], DT)
    hits = engine.check_strikes(fighter, "B", now_ms=0.0)
    assert hits == []
    assert engine.damage.hp["B"] == 100


def test_miss_does_not_register():
    engine, fighter = make_engine()
    # Fast punch far from any pole zone
    fighter.update(make_pose(right_wrist=(0.10, 0.48))[:, :2], DT)
    fighter.update(make_pose(right_wrist=(0.25, 0.48))[:, :2], DT)
    assert engine.check_strikes(fighter, "B", now_ms=0.0) == []


def test_hit_cooldown_blocks_repeat_then_expires():
    engine, fighter = make_engine()
    assert len(punch_pole(engine, fighter, now_ms=0.0)) == 1
    # Same limb-pair inside the 600ms cooldown window: suppressed
    assert punch_pole(engine, fighter, now_ms=200.0) == []
    # After cooldown expires: registers again
    assert len(punch_pole(engine, fighter, now_ms=700.0)) == 1


def test_block_detection_geometry():
    strike_from_right = np.array([0.62, 0.35])
    # Defender at cx=0.5 with right wrist raised above shoulders, between
    # the strike point and their torso center -> blocked
    guard = make_pose(right_wrist=(0.55, 0.25))[:, :2]
    assert sm.is_blocking(guard, strike_from_right)
    # Hands down at the waist -> not blocked
    idle = make_pose()[:, :2]
    assert not sm.is_blocking(idle, strike_from_right)
