"""Main menu: mode select with a VS Mode (Host/Join) submenu, room-token
entry, the pre-fight start screen, and the match creator's settings panel.
All screens draw over the fight-scene backdrop for a consistent look.

Joining is token-only here (D-020): the token path covers LAN and internet
alike, and connects directly when it can. Joining a raw IP is still possible
via `--ip` for offline LAN parties and loopback testing.
"""

import pygame

from shadowclash.capture.synthetic_pose import SyntheticPoseDriver
from shadowclash.network.rendezvous_server import TOKEN_LEN
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

# (label, options shown, writer applying the chosen option index to config,
#  reader returning the current option index from config)
SETTING_ROWS = [
    (
        "Hand tracking (fingers)",
        ["Off: stylized hands, fastest", "On: real finger tracking"],
        lambda config, i: config["pose"].__setitem__("hand_tracking", bool(i)),
        lambda config: 1 if config["pose"].get("hand_tracking") else 0,
    ),
    (
        "Tracking model",
        ["Fast", "Balanced", "Accurate"],
        lambda config, i: config["pose"].__setitem__("model_complexity", i),
        lambda config: min(config["pose"].get("model_complexity", 0), 2),
    ),
    (
        "Camera FPS",
        ["15", "30", "60"],
        lambda config, i: config["camera"].__setitem__("fps", [15, 30, 60][i]),
        lambda config: {15: 0, 30: 1, 60: 2}.get(config["camera"].get("fps", 30), 1),
    ),
]

# Extra row for the VS Mode host: how many rounds the match runs (best of N)
ROUNDS_ROW = (
    "Rounds (best of)",
    ["3", "5", "7"],
    lambda config, i: config["match"].__setitem__("vs_rounds", [3, 5, 7][i]),
    lambda config: {3: 0, 5: 1, 7: 2}.get(config["match"].get("vs_rounds", 3), 0),
)


def run_settings_panel(
    screen: pygame.Surface,
    config: dict,
    mode_label: str,
    subtitle: str,
    rows: list | None = None,
) -> bool:
    """Match creator's settings panel + START button.

    The game title stays SHADOWCLASH; `mode_label` names the mode beneath it.
    Shown before the camera turns on for single-player and host modes. The
    chosen values are written back into `config` when START is pressed.
    Returns True to start, False if the user quit.
    """
    clock = pygame.time.Clock()
    backdrop = FightScene(screen.get_size())
    small = theme.font(30)

    rows = SETTING_ROWS if rows is None else rows
    values = [read(config) for _, _, _, read in rows]
    selected = 0  # 0..len(rows)-1 = rows, len(rows) = START
    start_row = len(rows)
    cx = screen.get_width() // 2
    rows_top = 260
    row_h = 64
    button = pygame.Rect(0, 0, 340, 80)

    def row_rect(i: int) -> pygame.Rect:
        half = min(450, screen.get_width() // 2 - 20)
        return pygame.Rect(cx - half + 30, rows_top + i * row_h - 8, half * 2 - 60, row_h - 12)

    def cycle(i: int, direction: int) -> None:
        values[i] = (values[i] + direction) % len(rows[i][1])

    def apply_and_start() -> bool:
        for (label, options, write, _read), value in zip(rows, values):
            write(config, value)
        return True

    while True:
        cx = screen.get_width() // 2
        if backdrop.size != screen.get_size():
            backdrop = FightScene(screen.get_size())
        button.center = (cx, rows_top + start_row * row_h + 90)
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
        half = min(450, screen.get_width() // 2 - 20)
        panel = pygame.Rect(cx - half, rows_top - 60, half * 2, len(rows) * row_h + 70)
        theme.draw_panel(screen, panel)
        head = small.render(f"{mode_label} SETTINGS", True, theme.HIGHLIGHT)
        screen.blit(head, head.get_rect(midtop=(cx, rows_top - 46)))

        for i, (label, options, _write, _read) in enumerate(rows):
            rect = row_rect(i)
            if rect.collidepoint(mouse):
                selected = i
            if selected == i:
                pygame.draw.rect(screen, (44, 38, 58), rect, border_radius=8)
                pygame.draw.rect(screen, theme.HIGHLIGHT, rect, 2, border_radius=8)
            label_color = theme.HIGHLIGHT if selected == i else theme.TEXT
            label_surf = theme.render_fit(label, 40, label_color, int(rect.width * 0.42))
            screen.blit(label_surf, (rect.x + 16, rect.centery - label_surf.get_height() // 2))
            value_surf = theme.render_fit(
                "<  " + options[values[i]] + "  >", 40, theme.VALUE, int(rect.width * 0.52)
            )
            screen.blit(value_surf, value_surf.get_rect(midright=(rect.right - 16, rect.centery)))

        hover = button.collidepoint(mouse) or selected == start_row
        theme.draw_button(screen, button, "START", hover)
        hint = theme.render_fit(
            "arrows/WASD navigate, left/right or click changes a setting, START turns on the camera",
            30, theme.TEXT_DIM, screen.get_width() - 60,
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

        if backdrop.size != screen.get_size():
            backdrop = FightScene(screen.get_size())
        backdrop.draw_background(screen)
        theme.draw_title(screen, "SHADOWCLASH", "who is fighting?")
        panel = pygame.Rect(0, 0, min(620, screen.get_width() - 60), 150)
        panel.center = screen.get_rect().center
        theme.draw_panel(screen, panel)
        head = small.render("ENTER YOUR NAME", True, theme.HIGHLIGHT)
        screen.blit(head, head.get_rect(midtop=(panel.centerx, panel.y + 16)))
        prompt = theme.render_fit((name or "PLAYER") + "_", 48, theme.TEXT, panel.width - 40)
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

    while True:
        if backdrop.size != screen.get_size():
            backdrop = FightScene(screen.get_size())
        button.center = (screen.get_width() // 2, int(screen.get_height() * 0.62))
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
        mode_surf = theme.render_fit(mode_label, 44, theme.HIGHLIGHT, screen.get_width() - 60)
        screen.blit(mode_surf, mode_surf.get_rect(midtop=(screen.get_width() // 2, 200)))
        theme.draw_button(screen, button, "START", hover)
        hint = theme.render_fit(
            "click START or press Space to turn on tracking, Esc quits",
            30, theme.TEXT_DIM, screen.get_width() - 60,
        )
        screen.blit(hint, hint.get_rect(midtop=(button.centerx, button.bottom + 20)))

        pygame.display.flip()
        clock.tick(30)


def run_menu(config: dict) -> tuple[str, str | None]:
    """Returns (mode, ip). ip is set only for join mode."""
    pygame.init()
    disp = config["display"]
    screen = pygame.display.set_mode((disp["width"], disp["height"]), pygame.RESIZABLE)
    pygame.display.set_caption("SHADOWCLASH")
    clock = pygame.time.Clock()
    backdrop = FightScene(screen.get_size())
    mascot = SyntheticPoseDriver(seed=11, attack_interval=(1.2, 2.4))
    font = theme.font(48)
    small = theme.font(30)
    cx = screen.get_width() // 2

    items = MAIN_ITEMS
    selected = 0
    entering_token = False
    token_text = ""

    def panel_rect() -> pygame.Rect:
        rect = pygame.Rect(0, 0, 560, len(items) * 70 + 50)
        rect.midtop = (cx, 260)
        return rect

    def item_rect(i: int) -> pygame.Rect:
        panel = panel_rect()
        return pygame.Rect(panel.x + 20, panel.y + 22 + i * 70, panel.width - 40, 58)

    def activate(i: int) -> tuple[str, str | None] | None:
        nonlocal entering_token, items, selected
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
            entering_token = True
            return None
        return mode, None

    while True:
        cx = screen.get_width() // 2
        if backdrop.size != screen.get_size():
            backdrop = FightScene(screen.get_size())
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit", None
            if entering_token:
                if event.type != pygame.KEYDOWN:
                    continue
                if event.key == pygame.K_RETURN and token_text:
                    return "join", token_text
                elif event.key == pygame.K_ESCAPE:
                    entering_token = False
                    token_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    token_text = token_text[:-1]
                elif event.unicode.isalnum() and len(token_text) < TOKEN_LEN:
                    token_text += event.unicode.upper()
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

        if entering_token:
            token_panel = pygame.Rect(0, 0, min(820, screen.get_width() - 60), 150)
            token_panel.center = screen.get_rect().center
            theme.draw_panel(screen, token_panel)
            prompt = theme.render_fit(
                "Room token: " + token_text + "_", 48, theme.TEXT, token_panel.width - 40
            )
            screen.blit(prompt, prompt.get_rect(center=(token_panel.centerx, token_panel.centery - 20)))
            hint = theme.render_fit(
                f"the {TOKEN_LEN}-letter code from the host's screen, Enter to connect",
                30, theme.TEXT_DIM, token_panel.width - 40,
            )
            screen.blit(hint, hint.get_rect(midtop=(token_panel.centerx, token_panel.centery + 20)))
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
