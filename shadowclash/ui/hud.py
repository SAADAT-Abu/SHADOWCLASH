"""HUD: health bars, round timer, hit popups, debug overlay, KO screen."""

import time

import pygame

ZONE_COLORS = {"head": (255, 80, 80), "torso": (255, 170, 70), "leg": (230, 230, 100)}


class Hud:
    def __init__(self, screen: pygame.Surface):
        self.screen = screen
        self.font = pygame.font.Font(None, 28)
        self.big_font = pygame.font.Font(None, 96)
        self.popups: list[tuple[float, str, tuple[int, int, int], tuple[int, int]]] = []

    def add_hit_popup(self, zone: str, damage: float, blocked: bool, pos_px: tuple[int, int]) -> None:
        label = f"{'BLOCKED ' if blocked else ''}{zone.upper()} -{damage:.1f}"
        self.popups.append((time.monotonic(), label, ZONE_COLORS[zone], pos_px))

    def draw_health_bar(self, name: str, hp: float, max_hp: float, right: bool = False) -> None:
        w, h = 380, 26
        margin = 30
        x = self.screen.get_width() - w - margin if right else margin
        frac = max(hp / max_hp, 0.0)
        color = (80, 220, 80) if frac > 0.4 else (230, 180, 60) if frac > 0.15 else (230, 70, 70)
        fill_w = int(w * frac)
        pygame.draw.rect(self.screen, (50, 50, 50), (x, margin, w, h))
        fill_x = x + w - fill_w if right else x
        pygame.draw.rect(self.screen, color, (fill_x, margin, fill_w, h))
        pygame.draw.rect(self.screen, (255, 255, 255), (x, margin, w, h), 2)
        label = self.font.render(f"{name}  {hp:.0f}", True, (255, 255, 255))
        self.screen.blit(label, (x + 6, margin + h + 4))

    def draw_timer(self, seconds_left: float) -> None:
        text = self.big_font.render(f"{max(int(seconds_left), 0)}", True, (255, 255, 255))
        self.screen.blit(text, text.get_rect(midtop=(self.screen.get_width() // 2, 14)))

    def draw_popups(self) -> None:
        now = time.monotonic()
        self.popups = [p for p in self.popups if now - p[0] < 1.2]
        for start, label, color, (x, y) in self.popups:
            age = now - start
            surf = self.font.render(label, True, color)
            self.screen.blit(surf, (x, y - int(age * 50)))

    def draw_debug(self, lines: list[str]) -> None:
        y = self.screen.get_height() - 20 * len(lines) - 10
        for line in lines:
            surf = self.font.render(line, True, (160, 160, 160))
            self.screen.blit(surf, (10, y))
            y += 20

    def draw_center_message(self, text: str, sub: str | None = None) -> None:
        cx = self.screen.get_width() // 2
        cy = self.screen.get_height() // 2
        surf = self.big_font.render(text, True, (255, 60, 60))
        self.screen.blit(surf, surf.get_rect(center=(cx, cy)))
        if sub:
            sub_surf = self.font.render(sub, True, (255, 255, 255))
            self.screen.blit(sub_surf, sub_surf.get_rect(center=(cx, cy + 70)))
