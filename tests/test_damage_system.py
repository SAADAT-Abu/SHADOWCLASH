import pytest

from shadowclash.physics.damage_system import DamageSystem, compute_damage

CONFIG = {
    "damage": {"head": 15, "torso": 8, "leg": 4, "block_reduction": 0.7},
    "physics": {
        "min_strike_velocity": 3.0,
        "reference_velocity": 6.0,
        "max_damage_multiplier": 1.5,
        "hit_cooldown_ms": 600,
    },
    "match": {"starting_hp": 100, "round_time_seconds": 99},
}


def test_damage_scales_with_velocity():
    dmg = compute_damage(10, velocity=3.0, reference_velocity=6.0, max_multiplier=1.5,
                         blocked=False, block_reduction=0.7)
    assert dmg == pytest.approx(5.0)


def test_damage_multiplier_is_capped():
    dmg = compute_damage(10, velocity=60.0, reference_velocity=6.0, max_multiplier=1.5,
                         blocked=False, block_reduction=0.7)
    assert dmg == pytest.approx(15.0)


def test_block_reduces_damage():
    dmg = compute_damage(10, velocity=6.0, reference_velocity=6.0, max_multiplier=1.5,
                         blocked=True, block_reduction=0.7)
    assert dmg == pytest.approx(3.0)


def test_zone_base_damage():
    system = DamageSystem(CONFIG)
    # velocity == reference -> multiplier exactly 1.0
    head = system.apply_hit("A", "B", "head", velocity=6.0)
    assert head.damage == pytest.approx(15.0)
    torso = system.apply_hit("A", "B", "torso", velocity=6.0)
    assert torso.damage == pytest.approx(8.0)
    leg = system.apply_hit("A", "B", "leg", velocity=6.0)
    assert leg.damage == pytest.approx(4.0)
    assert system.hp["B"] == pytest.approx(100 - 15 - 8 - 4)
    assert system.hp["A"] == 100


def test_ko_and_hp_floor():
    system = DamageSystem(CONFIG)
    for _ in range(10):
        result = system.apply_hit("A", "B", "head", velocity=60.0)
    assert system.hp["B"] == 0.0
    assert result.ko is True
    assert system.is_ko("B")


def test_heal_caps_at_starting_hp():
    system = DamageSystem(CONFIG)
    system.apply_damage("B", 10)
    system.heal("B", 500)
    assert system.hp["B"] == 100.0


def test_reset():
    system = DamageSystem(CONFIG)
    system.apply_damage("A", 50)
    system.reset("A")
    assert system.hp["A"] == 100.0
