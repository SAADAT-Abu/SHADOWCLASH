"""Strike detection: point queries from striking limbs against receive shapes,
velocity gating, per-limb-pair cooldowns, block detection, damage dispatch.
"""

import numpy as np
import pymunk

from shadowclash.physics.damage_system import DamageSystem, HitResult
from shadowclash.physics.hitbox_manager import CATEGORY, QUERY_ALL, FighterHitboxes
from shadowclash.skeleton import skeleton_model as sm


class CooldownRegistry:
    """Per-key cooldown gate (key = striking limb x receiving zone)."""

    def __init__(self, cooldown_ms: float):
        self.cooldown_ms = cooldown_ms
        self._last_hit: dict[tuple, float] = {}

    def ready(self, key: tuple, now_ms: float) -> bool:
        last = self._last_hit.get(key)
        if last is not None and now_ms - last < self.cooldown_ms:
            return False
        self._last_hit[key] = now_ms
        return True


class CollisionEngine:
    def __init__(self, config: dict, damage_system: DamageSystem):
        phys = config["physics"]
        self.min_strike_velocity = phys["min_strike_velocity"]
        self.cooldowns = CooldownRegistry(phys["hit_cooldown_ms"])
        self.damage = damage_system
        self.space = pymunk.Space()
        # Debug/tuning info for the overlay
        self.last_hit: HitResult | None = None
        self.max_velocity_seen = 0.0

    def check_strikes(
        self,
        attacker: FighterHitboxes,
        defender_name: str,
        now_ms: float,
        defender_xy: np.ndarray | None = None,
    ) -> list[HitResult]:
        """Test every striking limb of `attacker` against `defender_name`'s
        receive shapes. `defender_xy` (arena pose) enables block detection;
        pass None for the pole.
        """
        hits: list[HitResult] = []
        query_filter = pymunk.ShapeFilter(categories=QUERY_ALL, mask=CATEGORY[defender_name])
        radius = attacker.strike_radius()

        for limb, (pos, velocity) in attacker.strikes.items():
            self.max_velocity_seen = max(self.max_velocity_seen, velocity)
            if velocity < self.min_strike_velocity:
                continue
            for info in self.space.point_query(tuple(pos), radius, query_filter):
                zone = info.shape.zone
                if not self.cooldowns.ready((attacker.name, limb, defender_name, zone), now_ms):
                    continue
                blocked = False
                if defender_xy is not None and zone in (sm.ZONE_HEAD, sm.ZONE_TORSO):
                    blocked = sm.is_blocking(defender_xy, pos)
                result = self.damage.apply_hit(attacker.name, defender_name, zone, velocity, blocked)
                self.last_hit = result
                hits.append(result)
        return hits
