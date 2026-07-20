"""Tekken-style zone damage, HP tracking and KO detection."""

from dataclasses import dataclass


@dataclass
class HitResult:
    attacker: str
    defender: str
    zone: str
    damage: float
    blocked: bool
    ko: bool


def compute_damage(
    base_damage: float,
    velocity: float,
    reference_velocity: float,
    max_multiplier: float,
    blocked: bool,
    block_reduction: float,
) -> float:
    """Damage formula: base * velocity multiplier (capped), reduced on block."""
    multiplier = min(velocity / reference_velocity, max_multiplier)
    damage = base_damage * multiplier
    if blocked:
        damage *= 1.0 - block_reduction
    return damage


class DamageSystem:
    def __init__(self, config: dict, fighters: tuple[str, str] = ("A", "B")):
        dmg = config["damage"]
        phys = config["physics"]
        self.base_damage = {"head": dmg["head"], "torso": dmg["torso"], "leg": dmg["leg"]}
        self.block_reduction = dmg["block_reduction"]
        self.reference_velocity = phys["reference_velocity"]
        self.max_multiplier = phys["max_damage_multiplier"]
        self.starting_hp = config["match"]["starting_hp"]
        self.hp = {f: float(self.starting_hp) for f in fighters}
        # Mode-level damage multiplier (VS mode softens hits so fights last)
        self.scale = 1.0

    def apply_hit(
        self, attacker: str, defender: str, zone: str, velocity: float, blocked: bool = False
    ) -> HitResult:
        damage = compute_damage(
            self.base_damage[zone],
            velocity,
            self.reference_velocity,
            self.max_multiplier,
            blocked,
            self.block_reduction,
        ) * self.scale
        self.apply_damage(defender, damage)
        return HitResult(attacker, defender, zone, damage, blocked, self.is_ko(defender))

    def apply_damage(self, defender: str, damage: float) -> None:
        self.hp[defender] = max(0.0, self.hp[defender] - damage)

    def heal(self, fighter: str, amount: float) -> None:
        self.hp[fighter] = min(float(self.starting_hp), self.hp[fighter] + amount)

    def is_ko(self, fighter: str) -> bool:
        return self.hp[fighter] <= 0.0

    def reset(self, fighter: str | None = None) -> None:
        for f in [fighter] if fighter else list(self.hp):
            self.hp[f] = float(self.starting_hp)
