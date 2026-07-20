"""Fight scene: layered dusk-dojo background, fighter shadows, hit sparks.

The background is rendered once into a cached surface (gradient sky, moon,
mountain and pagoda silhouettes, plank floor, hanging lanterns, vignette)
and blitted every frame. Hit sparks are lightweight additive particles.
"""

import math
import random

import numpy as np
import pygame

from shadowclash.skeleton import skeleton_model as sm
from shadowclash.ui import theme

FLOOR_Y = 0.78  # fraction of screen height where the floor starts


class FightScene:
    def __init__(self, size: tuple[int, int]):
        self.size = size
        self.background = self._build_background(size)
        self._particles: list[dict] = []
        self._rng = random.Random(9)

    # ------------------------------------------------------------------
    def _build_background(self, size: tuple[int, int]) -> pygame.Surface:
        w, h = size
        bg = theme.vertical_gradient(size)
        floor_y = int(h * FLOOR_Y)

        # Moon with soft glow
        moon = (int(w * 0.82), int(h * 0.16))
        for radius, alpha in ((90, 18), (66, 28), (46, 255)):
            glow = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(glow, (250, 240, 210, alpha), (radius, radius), radius)
            bg.blit(glow, (moon[0] - radius, moon[1] - radius))

        # Far mountain ridge
        ridge = [(0, floor_y)]
        for i in range(0, 11):
            x = w * i / 10
            y = floor_y - h * (0.10 + 0.06 * math.sin(i * 1.7) + 0.03 * math.sin(i * 3.1))
            ridge.append((int(x), int(y)))
        ridge.append((w, floor_y))
        pygame.draw.polygon(bg, (30, 20, 42), ridge)

        # Pagoda silhouette on the ridge
        px, py = int(w * 0.14), floor_y - int(h * 0.10)
        col = (18, 12, 26)
        for tier in range(3):
            tw = int(w * (0.085 - tier * 0.022))
            ty = py - tier * int(h * 0.045)
            pygame.draw.polygon(
                bg, col,
                [(px - tw, ty), (px + tw, ty), (px + int(tw * 0.55), ty - int(h * 0.028)),
                 (px - int(tw * 0.55), ty - int(h * 0.028))],
            )
            pygame.draw.rect(bg, col, (px - int(tw * 0.5), ty, tw, int(h * 0.02)))

        # Plank floor with perspective seams
        pygame.draw.rect(bg, theme.FLOOR_DARK, (0, floor_y, w, h - floor_y))
        vanish = (w // 2, int(h * 0.55))
        for i in range(-8, 9):
            x_bottom = w // 2 + i * int(w * 0.09)
            pygame.draw.line(bg, theme.FLOOR_LIGHT, vanish, (x_bottom, h), 2)
        for frac in (0.82, 0.87, 0.93):
            y = int(h * frac)
            pygame.draw.line(bg, theme.FLOOR_LIGHT, (0, y), (w, y), 2)
        pygame.draw.line(bg, (110, 80, 60), (0, floor_y), (w, floor_y), 4)

        # Hanging lanterns
        for lx in (0.08, 0.30, 0.70, 0.92):
            x = int(w * lx)
            drop = int(h * (0.06 + 0.02 * math.sin(lx * 20)))
            pygame.draw.line(bg, (60, 50, 70), (x, 0), (x, drop), 2)
            glow = pygame.Surface((44, 44), pygame.SRCALPHA)
            pygame.draw.circle(glow, (255, 160, 70, 40), (22, 22), 22)
            pygame.draw.circle(glow, (255, 190, 90, 180), (22, 22), 10)
            bg.blit(glow, (x - 22, drop - 6))

        # Vignette: darken edges
        vignette = pygame.Surface(size, pygame.SRCALPHA)
        for i in range(40):
            alpha = int(2.2 * (40 - i))
            pygame.draw.rect(vignette, (0, 0, 0, alpha), (i * 4, i * 3, w - i * 8, h - i * 6), 6)
        bg.blit(vignette, (0, 0))
        return bg

    # ------------------------------------------------------------------
    def draw_background(self, surface: pygame.Surface) -> None:
        surface.blit(self.background, (0, 0))

    def draw_fighter_shadow(
        self, surface: pygame.Surface, xy: np.ndarray, arena_rect: pygame.Rect
    ) -> None:
        """Soft ellipse under the fighter's feet, grounding them on the floor."""
        feet_x = (xy[sm.LEFT_ANKLE, 0] + xy[sm.RIGHT_ANKLE, 0]) / 2.0
        feet_y = max(xy[sm.LEFT_ANKLE, 1], xy[sm.RIGHT_ANKLE, 1])
        cx = int(arena_rect.x + feet_x * arena_rect.width)
        cy = int(arena_rect.y + min(feet_y + 0.03, 0.97) * arena_rect.height)
        width = int(sm.torso_length(xy) * arena_rect.height * 1.1)
        shadow = pygame.Surface((width * 2, width // 2), pygame.SRCALPHA)
        pygame.draw.ellipse(shadow, (0, 0, 0, 90), shadow.get_rect())
        surface.blit(shadow, (cx - width, cy - width // 4))

    # ------------------------------------------------------------------
    def add_hit_spark(self, pos_px: tuple[int, int], heavy: bool = False) -> None:
        count = 22 if heavy else 12
        base_color = (255, 200, 80) if heavy else (255, 160, 90)
        for _ in range(count):
            angle = self._rng.uniform(0, math.tau)
            speed = self._rng.uniform(120, 420 if heavy else 300)
            self._particles.append(
                {
                    "pos": [float(pos_px[0]), float(pos_px[1])],
                    "vel": [math.cos(angle) * speed, math.sin(angle) * speed - 60],
                    "life": self._rng.uniform(0.25, 0.5),
                    "age": 0.0,
                    "color": base_color,
                    "size": self._rng.randint(2, 5 if heavy else 4),
                }
            )

    def update_and_draw_particles(self, surface: pygame.Surface, dt: float) -> None:
        alive = []
        for p in self._particles:
            p["age"] += dt
            if p["age"] >= p["life"]:
                continue
            p["vel"][1] += 500 * dt  # gravity
            p["pos"][0] += p["vel"][0] * dt
            p["pos"][1] += p["vel"][1] * dt
            fade = 1.0 - p["age"] / p["life"]
            size = max(1, int(p["size"] * fade))
            spark = pygame.Surface((size * 2, size * 2), pygame.SRCALPHA)
            color = (*p["color"], int(255 * fade))
            pygame.draw.circle(spark, color, (size, size), size)
            surface.blit(spark, (int(p["pos"][0]) - size, int(p["pos"][1]) - size),
                         special_flags=pygame.BLEND_ALPHA_SDL2)
            alive.append(p)
        self._particles = alive
