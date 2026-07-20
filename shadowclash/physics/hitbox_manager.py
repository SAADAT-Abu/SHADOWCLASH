"""Pymunk hitbox management for fighters and the training pole.

Receiving zones (head / torso / legs) are shapes in the pymunk space, moved
to the latest landmark positions every frame. Striking limbs (fists / feet)
are tracked as points with velocities and tested against receiving shapes by
point queries (see DECISIONS.md D-010). All coordinates are normalized arena
units; velocities are torso-lengths per second (D-005).
"""

import numpy as np
import pymunk

from shadowclash.skeleton import skeleton_model as sm

# Collision filter categories for receiving shapes, per fighter slot
CATEGORY = {"A": 0b01, "B": 0b10}
QUERY_ALL = 0xFFFFFFFF


class FighterHitboxes:
    """Receive shapes + strike-limb tracking for one pose-driven fighter."""

    def __init__(self, space: pymunk.Space, name: str):
        self.space = space
        self.name = name
        self.body = pymunk.Body(body_type=pymunk.Body.STATIC)
        space.add(self.body)
        self._filter = pymunk.ShapeFilter(categories=CATEGORY[name], mask=QUERY_ALL)
        self._shapes_built = False
        self.head: pymunk.Circle | None = None
        self.torso: pymunk.Segment | None = None
        self.legs: dict[str, pymunk.Segment] = {}
        # limb name -> (position xy, velocity in torso-lengths/sec)
        self.strikes: dict[str, tuple[np.ndarray, float]] = {}
        self._prev_strike_pos: dict[str, np.ndarray] = {}
        self.xy: np.ndarray | None = None
        self.torso_len: float = 0.2

    def _build_shapes(self, xy: np.ndarray) -> None:
        self.head = pymunk.Circle(self.body, sm.head_radius(xy), tuple(sm.head_center(xy)))
        top, bottom, radius = sm.torso_endpoints(xy)
        self.torso = pymunk.Segment(self.body, tuple(top), tuple(bottom), radius)
        for leg, (knee, ankle) in sm.LEG_SEGMENTS.items():
            self.legs[leg] = pymunk.Segment(
                self.body, tuple(xy[knee]), tuple(xy[ankle]), sm.leg_radius(xy)
            )
        for shape, zone in self._zone_shapes():
            shape.sensor = True
            shape.filter = self._filter
            shape.owner = self.name
            shape.zone = zone
            self.space.add(shape)
        self._shapes_built = True

    def _zone_shapes(self) -> list[tuple[pymunk.Shape, str]]:
        return [
            (self.head, sm.ZONE_HEAD),
            (self.torso, sm.ZONE_TORSO),
            *[(shape, sm.ZONE_LEG) for shape in self.legs.values()],
        ]

    def update(self, xy: np.ndarray, dt: float) -> None:
        """Move receive shapes to the new pose and refresh strike velocities."""
        self.xy = xy
        self.torso_len = sm.torso_length(xy)
        if not self._shapes_built:
            self._build_shapes(xy)

        self.head.unsafe_set_offset(tuple(sm.head_center(xy)))
        self.head.unsafe_set_radius(sm.head_radius(xy))
        top, bottom, radius = sm.torso_endpoints(xy)
        self.torso.unsafe_set_endpoints(tuple(top), tuple(bottom))
        self.torso.unsafe_set_radius(radius)
        for leg, (knee, ankle) in sm.LEG_SEGMENTS.items():
            self.legs[leg].unsafe_set_endpoints(tuple(xy[knee]), tuple(xy[ankle]))
            self.legs[leg].unsafe_set_radius(sm.leg_radius(xy))
        self.space.reindex_shapes_for_body(self.body)

        for limb, idx in sm.STRIKE_LIMBS.items():
            pos = xy[idx].copy()
            prev = self._prev_strike_pos.get(limb)
            velocity = 0.0
            if prev is not None and dt > 0:
                velocity = float(np.linalg.norm(pos - prev) / dt / self.torso_len)
            self._prev_strike_pos[limb] = pos
            self.strikes[limb] = (pos, velocity)

    def strike_radius(self) -> float:
        return sm.strike_radius(self.xy) if self.xy is not None else 0.02


class PoleHitboxes:
    """Static training pole: three stacked receive circles (head/torso/leg)."""

    ZONES = {
        sm.ZONE_HEAD: (0.72, 0.30, 0.055),
        sm.ZONE_TORSO: (0.72, 0.48, 0.085),
        sm.ZONE_LEG: (0.72, 0.72, 0.075),
    }

    def __init__(self, space: pymunk.Space, name: str = "B"):
        self.name = name
        body = pymunk.Body(body_type=pymunk.Body.STATIC)
        space.add(body)
        for zone, (x, y, r) in self.ZONES.items():
            shape = pymunk.Circle(body, r, (x, y))
            shape.sensor = True
            shape.filter = pymunk.ShapeFilter(categories=CATEGORY[name], mask=QUERY_ALL)
            shape.owner = name
            shape.zone = zone
            space.add(shape)
