"""Pygame stick-figure rendering of a fighter from arena-space landmarks."""

import numpy as np
import pygame

from shadowclash.skeleton import skeleton_model as sm


def _draw_hand(
    surface: pygame.Surface,
    xy: np.ndarray,
    hand: tuple[int, int, int, int],
    color: tuple[int, int, int],
    px,
    finger_w: int,
) -> None:
    """Palm polygon + stylized fingers. MediaPipe Pose only provides knuckle
    landmarks (thumb/index/pinky), so fingertips are extrapolated outward
    from the wrist through the knuckle line.
    """
    wrist_i, thumb_i, index_i, pinky_i = hand
    wrist, thumb, index, pinky = xy[wrist_i], xy[thumb_i], xy[index_i], xy[pinky_i]

    palm = [px(wrist), px(thumb), px(index), px(pinky)]
    pygame.draw.polygon(surface, color, palm)
    pygame.draw.polygon(surface, _lighten(color), palm, 1)

    for frac in (0.0, 1.0 / 3.0, 2.0 / 3.0, 1.0):
        base = index + (pinky - index) * frac
        tip = base + (base - wrist) * 0.45
        pygame.draw.line(surface, color, px(base), px(tip), finger_w)
    thumb_tip = thumb + (thumb - wrist) * 0.4
    pygame.draw.line(surface, color, px(thumb), px(thumb_tip), finger_w)


def _lighten(color: tuple[int, int, int]) -> tuple[int, int, int]:
    return tuple(min(255, c + 70) for c in color)


def _draw_tracked_hand(
    surface: pygame.Surface,
    xy: np.ndarray,
    start: int,
    color: tuple[int, int, int],
    px,
    finger_w: int,
) -> None:
    """Full 21-landmark Holistic hand: real palm + per-finger bones."""
    pts = xy[start : start + sm.HAND_LANDMARKS]
    pygame.draw.polygon(surface, color, [px(pts[i]) for i in sm.HAND_PALM_IDX])
    for a, b in sm.HAND_CONNECTIONS:
        pygame.draw.line(surface, color, px(pts[a]), px(pts[b]), finger_w)
    for tip in (4, 8, 12, 16, 20):
        pygame.draw.circle(surface, color, px(pts[tip]), max(1, finger_w // 2))


def draw_skeleton(
    surface: pygame.Surface,
    xy: np.ndarray,
    color: tuple[int, int, int],
    arena_rect: pygame.Rect,
    visibility: np.ndarray | None = None,
) -> None:
    """Draw bones, joints, head, hands with fingers, feet and strike markers.

    xy is (N, 2) normalized arena coords (33 pose rows, optionally +42
    Holistic hand rows); arena_rect maps them to pixels. `visibility` is the
    matching (N,) visibility column, used to decide whether each hand has
    live finger tracking or falls back to the stylized knuckle hand.
    """

    def px(point: np.ndarray) -> tuple[int, int]:
        return (
            int(arena_rect.x + point[0] * arena_rect.width),
            int(arena_rect.y + point[1] * arena_rect.height),
        )

    scale = arena_rect.height
    torso_len = sm.torso_length(xy)
    bone_w = max(3, int(torso_len * scale * 0.10))
    finger_w = max(2, bone_w // 3)

    for a, b in sm.BONES:
        pygame.draw.line(surface, color, px(xy[a]), px(xy[b]), bone_w)

    # Rounded caps over bone ends so limbs bend smoothly instead of gapping
    joint_r = max(2, bone_w // 2)
    for idx in sm.JOINTS:
        pygame.draw.circle(surface, color, px(xy[idx]), joint_r)

    hand_starts = {"left": sm.LEFT_HAND_START, "right": sm.RIGHT_HAND_START}
    tracked = {}
    for side, hand in sm.HANDS.items():
        start = hand_starts[side]
        tracked[side] = visibility is not None and sm.hand_tracked(visibility, start)
        if tracked[side]:
            _draw_tracked_hand(surface, xy, start, color, px, finger_w)
        else:
            _draw_hand(surface, xy, hand, color, px, finger_w)

    for ankle, heel, toe in sm.FEET.values():
        foot = [px(xy[ankle]), px(xy[heel]), px(xy[toe])]
        pygame.draw.polygon(surface, color, foot)
        pygame.draw.polygon(surface, _lighten(color), foot, 1)

    center = sm.head_center(xy)
    radius = max(int(sm.head_radius(xy) * scale), 4)
    pygame.draw.circle(surface, color, px(center), radius)
    pygame.draw.circle(surface, _lighten(color), px(center), radius, 2)

    # Strike hitbox markers, centered on the visual hand/foot rather than
    # the raw wrist/ankle (physics still tracks the wrist/ankle landmark)
    def fist_center(side: str) -> np.ndarray:
        if tracked[side]:
            start = hand_starts[side]
            return xy[start : start + sm.HAND_LANDMARKS].mean(axis=0)
        wrist, _, index, pinky = sm.HANDS[side]
        return (xy[wrist] + xy[index] + xy[pinky]) / 3.0

    strike_centers = {
        "left_fist": fist_center("left"),
        "right_fist": fist_center("right"),
        "left_foot": (xy[sm.LEFT_ANKLE] + xy[sm.LEFT_FOOT_INDEX]) / 2.0,
        "right_foot": (xy[sm.RIGHT_ANKLE] + xy[sm.RIGHT_FOOT_INDEX]) / 2.0,
    }
    r = max(int(sm.strike_radius(xy) * scale), 3)
    for center_pt in strike_centers.values():
        pygame.draw.circle(surface, (255, 255, 255), px(center_pt), r, 2)


def draw_pole(
    surface: pygame.Surface,
    zones: dict[str, tuple[float, float, float]],
    hp_fraction: float,
    arena_rect: pygame.Rect,
) -> None:
    """Draw the training pole: stacked zone circles + a trunk line + HP bar."""
    scale = arena_rect.height

    def px(x: float, y: float) -> tuple[int, int]:
        return (int(arena_rect.x + x * arena_rect.width), int(arena_rect.y + y * arena_rect.height))

    xs = [z[0] for z in zones.values()]
    ys = [z[1] for z in zones.values()]
    pygame.draw.line(
        surface, (120, 90, 60), px(xs[0], min(ys) - 0.05), px(xs[0], 0.95), 10
    )
    colors = {"head": (220, 60, 60), "torso": (220, 140, 60), "leg": (200, 200, 80)}
    for zone, (x, y, r) in zones.items():
        pygame.draw.circle(surface, colors[zone], px(x, y), int(r * scale), 3)

    bar_w, bar_h = 120, 12
    bx, by = px(xs[0], min(ys) - 0.12)
    bx -= bar_w // 2
    pygame.draw.rect(surface, (60, 60, 60), (bx, by, bar_w, bar_h))
    pygame.draw.rect(surface, (80, 220, 80), (bx, by, int(bar_w * max(hp_fraction, 0)), bar_h))
    pygame.draw.rect(surface, (255, 255, 255), (bx, by, bar_w, bar_h), 1)
