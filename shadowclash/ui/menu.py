"""Main menu: mode select with a VS Mode (Host/Join) submenu, IP entry,
the pre-fight start screen, and the match creator's settings panel.
All screens draw over the fight-scene backdrop for a consistent look."""

import pygame

from shadowclash.capture.synthetic_pose import SyntheticPoseDriver
from shadowclash.skeleton import skeleton_model as sm
from shadowclash.skeleton.skeleton_renderer import draw_skeleton
from shadowclash.ui import theme
from shadowclash.ui.scene import FightScene

MAIN_ITEMS = [
    ("Single Player", "versus"),
    ("Training", "singleplayer"),
    ("VS Mode", "vs"),
    ("Quit", "quit"),
]
VS_ITEMS = [
    ("Host", "host"),
    ("Join", "join"),
    ("Back", "back"),
]

# (label, options shown, writer applying the chosen option index to config)
SETTING_ROWS = [
    (
        "Hand tracking (fingers)",
        ["Off: stylized hands, fastest", "On: real finger tracking"],
        lambda config, i: config["pose"].__setitem__("hand_tracking", bool(i)),
    ),
    (
        "Tracking model",
        ["Fast", "Balanced", "Accurate"],
        lambda config, i: config["pose"].__setitem__("model_complexity", i),
    ),
    (
        "Camera FPS",
        ["15", "30", "60"],
        lambda config, i: config["camera"].__setitem__("fps", [15, 30, 60][i]),
    ),
]


def _current_setting_values(config: dict) -> list[int]:
    return [
        1 if config["pose"].get("hand_tracking") else 0,
        min(config["pose"].get("model_complexity", 0), 2),
        {15: 0, 30: 1, 60: 2}.get(config["camera"].get("fps", 30), 1),
    ]


def run_settings_panel(screen: pygame.Surface, config: dict, mode_label: str, subtitle: str) -> bool:
    """Match creator's settings panel + START button.

    The game title stays SHADOWCLASH; `mode_label` names the mode beneath it.
    Shown before the camera turns on for single-player and host modes. The
    chosen values are written back into `config` when START is pressed.
    Returns True to start, False if the user quit.
    """
    clock = pygame.time.Clock()
    backdrop = FightScene(screen.get_size())
    row_font = theme.font(40)
    small = theme.font(30)

    values = _current_setting_values(config)
    selected = 0  # 0..len(SETTING_ROWS)-1 = rows, len(SETTING_ROWS) = START
    start_row = len(SETTING_ROWS)
    cx = screen.get_width() // 2
    rows_top = 260
    row_h = 64
    button = pygame.Rect(0, 0, 340, 80)
    button.center = (cx, rows_top + start_row * row_h + 90)

    def row_rect(i: int) -> pygame.Rect:
        return pygame.Rect(cx - 420, rows_top + i * row_h - 8, 840, row_h - 12)

    def cycle(i: int, direction: int) -> None:
        values[i] = (values[i] + direction) % len(SETTING_ROWS[i][1])

    def apply_and_start() -> bool:
        for (label, options, write), value in zip(SETTING_ROWS, values):
            write(config, value)
        return True

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % (start_row + 1)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % (start_row + 1)
                elif event.key in (pygame.K_LEFT, pygame.K_a) and selected < start_row:
                    cycle(selected, -1)
                elif event.key in (pygame.K_RIGHT, pygame.K_d) and selected < start_row:
                    cycle(selected, 1)
                elif event.key in (pygame.K_RETURN, pygame.K_SPACE):
                    if selected == start_row:
                        return apply_and_start()
                    cycle(selected, 1)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if button.collidepoint(event.pos):
                    return apply_and_start()
                for i in range(start_row):
                    if row_rect(i).collidepoint(event.pos):
                        selected = i
                        cycle(i, 1)

        mouse = pygame.mouse.get_pos()
        backdrop.draw_background(screen)
        theme.draw_title(screen, "SHADOWCLASH", subtitle)
        panel = pygame.Rect(cx - 450, rows_top - 60, 900, len(SETTING_ROWS) * row_h + 70)
        theme.draw_panel(screen, panel)
        head = small.render(f"{mode_label} SETTINGS", True, theme.HIGHLIGHT)
        screen.blit(head, head.get_rect(midtop=(cx, rows_top - 46)))

        for i, (label, options, _) in enumerate(SETTING_ROWS):
            rect = row_rect(i)
            if rect.collidepoint(mouse):
                selected = i
            if selected == i:
                pygame.draw.rect(screen, (44, 38, 58), rect, border_radius=8)
                pygame.draw.rect(screen, theme.HIGHLIGHT, rect, 2, border_radius=8)
            label_color = theme.HIGHLIGHT if selected == i else theme.TEXT
            label_surf = row_font.render(label, True, label_color)
            screen.blit(label_surf, (rect.x + 16, rect.y + 12))
            value_surf = row_font.render("<  " + options[values[i]] + "  >", True, theme.VALUE)
            screen.blit(value_surf, value_surf.get_rect(midright=(rect.right - 16, rect.centery)))

        hover = button.collidepoint(mouse) or selected == start_row
        theme.draw_button(screen, button, "START", hover)
        hint = small.render(
            "arrows/WASD navigate, left/right or click changes a setting, START turns on the camera",
            True,
            theme.TEXT_DIM,
        )
        screen.blit(hint, hint.get_rect(midtop=(cx, button.bottom + 18)))

        pygame.display.flip()
        clock.tick(30)


def run_name_entry(screen: pygame.Surface, config: dict) -> str | None:
    """Ask the player for their fight name (shown on the HUD and KO screen).

    Returns the name, or None if the player quit. Enter with an empty box
    uses PLAYER. The name is kept in config for this session so rematches
    and mode switches remember it.
    """
    clock = pygame.time.Clock()
    backdrop = FightScene(screen.get_size())
    font = theme.font(48)
    small = theme.font(30)
    name = str(config.get("player_name", ""))
    max_len = 12

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return None
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                return None
            if event.key == pygame.K_RETURN:
                final = name.strip() or "PLAYER"
                config["player_name"] = final
                return final
            if event.key == pygame.K_BACKSPACE:
                name = name[:-1]
            elif event.unicode and len(name) < max_len and (
                event.unicode.isalnum() or event.unicode in " -_"
            ):
                name += event.unicode.upper()

        backdrop.draw_background(screen)
        theme.draw_title(screen, "SHADOWCLASH", "who is fighting?")
        panel = pygame.Rect(0, 0, 620, 150)
        panel.center = screen.get_rect().center
        theme.draw_panel(screen, panel)
        head = small.render("ENTER YOUR NAME", True, theme.HIGHLIGHT)
        screen.blit(head, head.get_rect(midtop=(panel.centerx, panel.y + 16)))
        prompt = font.render((name or "PLAYER") + "_", True, theme.TEXT)
        screen.blit(prompt, prompt.get_rect(center=(panel.centerx, panel.centery + 12)))
        hint = small.render("Enter to confirm, Esc to cancel", True, theme.TEXT_DIM)
        screen.blit(hint, hint.get_rect(midtop=(panel.centerx, panel.bottom + 14)))

        pygame.display.flip()
        clock.tick(30)


def run_start_screen(screen: pygame.Surface, mode_label: str, subtitle: str) -> bool:
    """Show a START button; camera tracking begins only after it's pressed.

    The game title stays SHADOWCLASH; `mode_label` names the mode beneath it.
    Returns True to start, False if the user quit. Click the button or
    press Space/Enter to start; Esc or closing the window quits.
    """
    clock = pygame.time.Clock()
    backdrop = FightScene(screen.get_size())
    button = pygame.Rect(0, 0, 340, 90)
    button.center = (screen.get_width() // 2, int(screen.get_height() * 0.62))

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                    return True
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if button.collidepoint(event.pos):
                    return True

        hover = button.collidepoint(pygame.mouse.get_pos())
        backdrop.draw_background(screen)
        theme.draw_title(screen, "SHADOWCLASH", subtitle)
        mode_surf = theme.font(44).render(mode_label, True, theme.HIGHLIGHT)
        screen.blit(mode_surf, mode_surf.get_rect(midtop=(screen.get_width() // 2, 200)))
        theme.draw_button(screen, button, "START", hover)
        hint = theme.font(30).render(
            "click START or press Space to turn on tracking, Esc quits", True, theme.TEXT_DIM
        )
        screen.blit(hint, hint.get_rect(midtop=(button.centerx, button.bottom + 20)))

        pygame.display.flip()
        clock.tick(30)


def run_menu(config: dict) -> tuple[str, str | None]:
    """Returns (mode, ip). ip is set only for join mode."""
    pygame.init()
    disp = config["display"]
    screen = pygame.display.set_mode((disp["width"], disp["height"]))
    pygame.display.set_caption("SHADOWCLASH")
    clock = pygame.time.Clock()
    backdrop = FightScene(screen.get_size())
    mascot = SyntheticPoseDriver(seed=11, attack_interval=(1.2, 2.4))
    font = theme.font(48)
    small = theme.font(30)
    cx = screen.get_width() // 2

    items = MAIN_ITEMS
    selected = 0
    entering_ip = False
    ip_text = ""

    def panel_rect() -> pygame.Rect:
        rect = pygame.Rect(0, 0, 560, len(items) * 70 + 50)
        rect.midtop = (cx, 260)
        return rect

    def item_rect(i: int) -> pygame.Rect:
        panel = panel_rect()
        return pygame.Rect(panel.x + 20, panel.y + 22 + i * 70, panel.width - 40, 58)

    def activate(i: int) -> tuple[str, str | None] | None:
        nonlocal entering_ip, items, selected
        mode = items[i][1]
        if mode == "vs":
            items = VS_ITEMS
            selected = 0
            return None
        if mode == "back":
            items = MAIN_ITEMS
            selected = 0
            return None
        if mode == "join":
            entering_ip = True
            return None
        return mode, None

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit", None
            if entering_ip:
                if event.type != pygame.KEYDOWN:
                    continue
                if event.key == pygame.K_RETURN and ip_text:
                    return "join", ip_text
                elif event.key == pygame.K_ESCAPE:
                    entering_ip = False
                    ip_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    ip_text = ip_text[:-1]
                elif event.unicode and (event.unicode.isdigit() or event.unicode == "."):
                    ip_text += event.unicode
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    if items is VS_ITEMS:
                        items = MAIN_ITEMS
                        selected = 0
                    else:
                        return "quit", None
                elif event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(items)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(items)
                elif event.key == pygame.K_RETURN:
                    result = activate(selected)
                    if result is not None:
                        return result
            elif event.type == pygame.MOUSEMOTION:
                for i in range(len(items)):
                    if item_rect(i).collidepoint(event.pos):
                        selected = i
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for i in range(len(items)):
                    if item_rect(i).collidepoint(event.pos):
                        selected = i
                        result = activate(i)
                        if result is not None:
                            return result

        backdrop.draw_background(screen)

        # Live shadow fighter sparring in the backdrop
        mascot_pose, _ = mascot.get_pose()
        mascot_xy = sm.to_arena(mascot_pose, flip=True)
        mascot_xy[:, 0] += 0.18  # park it right of the panel, undistorted
        backdrop.draw_fighter_shadow(screen, mascot_xy, screen.get_rect())
        draw_skeleton(screen, mascot_xy, (58, 44, 74), screen.get_rect(),
                      visibility=mascot_pose[:, 3])

        theme.draw_title(
            screen, "SHADOWCLASH", "Your body is the controller. Your shadow is your fighter."
        )

        if entering_ip:
            ip_panel = pygame.Rect(0, 0, 620, 140)
            ip_panel.center = screen.get_rect().center
            theme.draw_panel(screen, ip_panel)
            prompt = font.render("Host IP: " + ip_text + "_", True, theme.TEXT)
            screen.blit(prompt, prompt.get_rect(center=(ip_panel.centerx, ip_panel.centery - 15)))
            hint = small.render("Enter to connect, Esc to cancel", True, theme.TEXT_DIM)
            screen.blit(hint, hint.get_rect(midtop=(ip_panel.centerx, ip_panel.centery + 25)))
        else:
            theme.draw_panel(screen, panel_rect())
            if items is VS_ITEMS:
                head = small.render("VS MODE", True, theme.TEXT_DIM)
                screen.blit(head, head.get_rect(midbottom=(cx, panel_rect().y - 8)))
            for i, (label, _) in enumerate(items):
                rect = item_rect(i)
                if i == selected:
                    pygame.draw.rect(screen, (44, 38, 58), rect, border_radius=8)
                    pygame.draw.rect(screen, theme.HIGHLIGHT, rect, 3, border_radius=8)
                color = theme.HIGHLIGHT if i == selected else theme.TEXT
                surf = font.render(label, True, color)
                screen.blit(surf, surf.get_rect(center=rect.center))
            footer = small.render(
                "arrows or mouse to choose, Enter or click to select, Esc to go back or quit",
                True,
                theme.TEXT_DIM,
            )
            screen.blit(
                footer,
                footer.get_rect(midbottom=(cx, screen.get_height() - 18)),
            )

        pygame.display.flip()
        clock.tick(30)
