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

    def draw_level_banner(self, text: str) -> None:
        surf = self.font.render(text, True, (255, 214, 90))
        self.screen.blit(surf, surf.get_rect(midtop=(self.screen.get_width() // 2, 92)))

    def draw_distance_hint(self, text: str) -> None:
        surf = self.font.render(text, True, (120, 200, 255))
        pos = surf.get_rect(midbottom=(self.screen.get_width() // 2, int(self.screen.get_height() * 0.97)))
        pygame.draw.rect(self.screen, (20, 18, 30), pos.inflate(24, 10), border_radius=8)
        self.screen.blit(surf, pos)

    def draw_debug(self, lines: list[str]) -> None:
        y = self.screen.get_height() - 20 * len(lines) - 10
        for line in lines:
            surf = self.font.render(line, True, (160, 160, 160))
            self.screen.blit(surf, (10, y))
            y += 20

    def draw_center_message(
        self, text: str, sub: str | None = None, color: tuple[int, int, int] = (255, 60, 60)
    ) -> None:
        from shadowclash.ui.theme import render_fit

        w = self.screen.get_width()
        cx, cy = w // 2, self.screen.get_height() // 2
        surf = render_fit(text, 96, color, w - 60)
        self.screen.blit(surf, surf.get_rect(center=(cx, cy)))
        if sub:
            sub_surf = render_fit(sub, 28, (255, 255, 255), w - 60)
            self.screen.blit(sub_surf, sub_surf.get_rect(center=(cx, cy + 70)))

    def draw_round_pips(self, wins: int, needed: int, right: bool = False) -> None:
        """Tekken-style round markers under a health bar: one pip per round
        needed to take the match, filled as rounds are won."""
        margin, bar_h, r, gap = 30, 26, 7, 22
        y = margin + bar_h + 36
        for i in range(needed):
            x = (
                self.screen.get_width() - margin - r - i * gap
                if right
                else margin + r + i * gap
            )
            if i < wins:
                pygame.draw.circle(self.screen, (255, 214, 90), (x, y), r)
            pygame.draw.circle(self.screen, (255, 255, 255), (x, y), r, 2)

    def draw_countdown(self, title: str, seconds: int, sub: str | None = None) -> None:
        from shadowclash.ui.theme import render_fit

        w = self.screen.get_width()
        cx, cy = w // 2, self.screen.get_height() // 2
        title_surf = render_fit(title, 72, (255, 214, 90), w - 60)
        self.screen.blit(title_surf, title_surf.get_rect(center=(cx, cy - 90)))
        num_surf = render_fit(str(seconds), 140, (255, 255, 255), w - 60)
        self.screen.blit(num_surf, num_surf.get_rect(center=(cx, cy + 10)))
        if sub:
            sub_surf = render_fit(sub, 28, (255, 255, 255), w - 60)
            self.screen.blit(sub_surf, sub_surf.get_rect(center=(cx, cy + 110)))
