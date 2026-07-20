"""Shared visual theme: palette, fonts, gradients, buttons, panels."""

import pygame

# Palette — dusk dojo
BG_TOP = (24, 16, 40)
BG_BOTTOM = (86, 34, 44)
FLOOR_DARK = (38, 26, 24)
FLOOR_LIGHT = (54, 38, 32)
ACCENT = (255, 96, 64)
TEXT = (235, 230, 224)
TEXT_DIM = (160, 152, 148)
HIGHLIGHT = (255, 214, 90)
VALUE = (120, 200, 255)
PANEL = (26, 22, 36)
BUTTON = (60, 160, 60)
BUTTON_HOVER = (90, 200, 90)

_fonts: dict[int, pygame.font.Font] = {}


def font(size: int) -> pygame.font.Font:
    if size not in _fonts:
        _fonts[size] = pygame.font.Font(None, size)
    return _fonts[size]


def render_fit(text: str, size: int, color: tuple[int, int, int], max_width: int) -> pygame.Surface:
    """Render text, stepping the font size down until it fits max_width."""
    surf = font(size).render(text, True, color)
    while surf.get_width() > max_width and size > 14:
        size -= 2
        surf = font(size).render(text, True, color)
    return surf


def vertical_gradient(
    size: tuple[int, int],
    top: tuple[int, int, int] = BG_TOP,
    bottom: tuple[int, int, int] = BG_BOTTOM,
) -> pygame.Surface:
    """Cheap smooth gradient: paint a 1x64 strip and smoothscale up."""
    strip = pygame.Surface((1, 64))
    for i in range(64):
        f = i / 63
        strip.set_at((0, i), tuple(int(t + (b - t) * f) for t, b in zip(top, bottom)))
    return pygame.transform.smoothscale(strip, size)


def draw_title(surface: pygame.Surface, title: str, subtitle: str | None = None) -> None:
    cx = surface.get_width() // 2
    shadow = font(96).render(title, True, (0, 0, 0))
    surface.blit(shadow, shadow.get_rect(midtop=(cx + 4, 74)))
    text = font(96).render(title, True, ACCENT)
    surface.blit(text, text.get_rect(midtop=(cx, 70)))
    if subtitle:
        sub = font(30).render(subtitle, True, TEXT_DIM)
        surface.blit(sub, sub.get_rect(midtop=(cx, 158)))


def draw_button(surface: pygame.Surface, rect: pygame.Rect, label: str, hover: bool) -> None:
    pygame.draw.rect(surface, BUTTON_HOVER if hover else BUTTON, rect, border_radius=12)
    pygame.draw.rect(surface, TEXT, rect, 3, border_radius=12)
    text = font(56).render(label, True, TEXT)
    surface.blit(text, text.get_rect(center=rect.center))


def draw_panel(surface: pygame.Surface, rect: pygame.Rect, alpha: int = 210) -> None:
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    panel.fill((*PANEL, alpha))
    surface.blit(panel, rect.topleft)
    pygame.draw.rect(surface, (90, 80, 100), rect, 2, border_radius=10)
