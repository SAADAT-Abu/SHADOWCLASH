"""Main menu: mode select + IP entry for joining, keyboard-driven.
Also the pre-fight start screen and the match creator's settings panel."""

import pygame

# (label, options shown, writer applying the chosen option index to config)
SETTING_ROWS = [
    (
        "Hand tracking (fingers)",
        ["Off — stylized hands, fastest", "On — real finger tracking"],
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


def run_settings_panel(screen: pygame.Surface, config: dict, title: str, subtitle: str) -> bool:
    """Match creator's settings panel + START button.

    Shown before the camera turns on for singleplayer and host modes. The
    chosen values are written back into `config` when START is pressed.
    Returns True to start, False if the user quit.
    """
    clock = pygame.time.Clock()
    title_font = pygame.font.Font(None, 90)
    row_font = pygame.font.Font(None, 40)
    button_font = pygame.font.Font(None, 56)
    small = pygame.font.Font(None, 30)

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
        screen.fill((14, 14, 20))
        title_surf = title_font.render(title, True, (255, 80, 60))
        screen.blit(title_surf, title_surf.get_rect(midtop=(cx, 70)))
        sub_surf = small.render(subtitle, True, (170, 170, 170))
        screen.blit(sub_surf, sub_surf.get_rect(midtop=(cx, 150)))
        head = small.render("MATCH SETTINGS", True, (120, 120, 130))
        screen.blit(head, head.get_rect(midtop=(cx, rows_top - 50)))

        for i, (label, options, _) in enumerate(SETTING_ROWS):
            rect = row_rect(i)
            active = selected == i or rect.collidepoint(mouse)
            if active:
                pygame.draw.rect(screen, (32, 32, 44), rect, border_radius=8)
            label_color = (255, 220, 90) if selected == i else (210, 210, 210)
            label_surf = row_font.render(label, True, label_color)
            screen.blit(label_surf, (rect.x + 16, rect.y + 12))
            value_surf = row_font.render("<  " + options[values[i]] + "  >", True, (120, 200, 255))
            screen.blit(value_surf, value_surf.get_rect(midright=(rect.right - 16, rect.centery)))

        hover = button.collidepoint(mouse) or selected == start_row
        pygame.draw.rect(screen, (90, 200, 90) if hover else (60, 160, 60), button, border_radius=12)
        pygame.draw.rect(screen, (255, 255, 255), button, 3, border_radius=12)
        label = button_font.render("START", True, (255, 255, 255))
        screen.blit(label, label.get_rect(center=button.center))
        hint = small.render(
            "arrows/WASD navigate — left/right or click changes a setting — START turns on the camera",
            True,
            (150, 150, 150),
        )
        screen.blit(hint, hint.get_rect(midtop=(cx, button.bottom + 18)))

        pygame.display.flip()
        clock.tick(30)


def run_start_screen(screen: pygame.Surface, title: str, subtitle: str) -> bool:
    """Show a START button; camera tracking begins only after it's pressed.

    Returns True to start, False if the user quit. Click the button or
    press Space/Enter to start; Esc or closing the window quits.
    """
    clock = pygame.time.Clock()
    title_font = pygame.font.Font(None, 90)
    button_font = pygame.font.Font(None, 56)
    small = pygame.font.Font(None, 30)
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
        screen.fill((14, 14, 20))
        title_surf = title_font.render(title, True, (255, 80, 60))
        screen.blit(title_surf, title_surf.get_rect(midtop=(screen.get_width() // 2, 90)))
        sub_surf = small.render(subtitle, True, (170, 170, 170))
        screen.blit(sub_surf, sub_surf.get_rect(midtop=(screen.get_width() // 2, 175)))

        pygame.draw.rect(screen, (90, 200, 90) if hover else (60, 160, 60), button, border_radius=12)
        pygame.draw.rect(screen, (255, 255, 255), button, 3, border_radius=12)
        label = button_font.render("START", True, (255, 255, 255))
        screen.blit(label, label.get_rect(center=button.center))
        hint = small.render("click START (or press Space) to turn on tracking — Esc quits", True, (150, 150, 150))
        screen.blit(hint, hint.get_rect(midtop=(button.centerx, button.bottom + 20)))

        pygame.display.flip()
        clock.tick(30)

MENU_ITEMS = [
    ("Training — Kicking Pole", "singleplayer"),
    ("Multiplayer — Host", "host"),
    ("Multiplayer — Join", "join"),
    ("Quit", "quit"),
]


def run_menu(config: dict) -> tuple[str, str | None]:
    """Returns (mode, ip). ip is set only for join mode."""
    pygame.init()
    disp = config["display"]
    screen = pygame.display.set_mode((disp["width"], disp["height"]))
    pygame.display.set_caption("SHADOWCLASH")
    clock = pygame.time.Clock()
    title_font = pygame.font.Font(None, 110)
    font = pygame.font.Font(None, 48)
    small = pygame.font.Font(None, 30)

    selected = 0
    entering_ip = False
    ip_text = ""

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return "quit", None
            if event.type != pygame.KEYDOWN:
                continue
            if entering_ip:
                if event.key == pygame.K_RETURN and ip_text:
                    return "join", ip_text
                elif event.key == pygame.K_ESCAPE:
                    entering_ip = False
                    ip_text = ""
                elif event.key == pygame.K_BACKSPACE:
                    ip_text = ip_text[:-1]
                elif event.unicode and (event.unicode.isdigit() or event.unicode == "."):
                    ip_text += event.unicode
            else:
                if event.key == pygame.K_ESCAPE:
                    return "quit", None
                elif event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(MENU_ITEMS)
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(MENU_ITEMS)
                elif event.key == pygame.K_RETURN:
                    mode = MENU_ITEMS[selected][1]
                    if mode == "join":
                        entering_ip = True
                    else:
                        return mode, None

        screen.fill((14, 14, 20))
        title = title_font.render("SHADOWCLASH", True, (255, 80, 60))
        screen.blit(title, title.get_rect(midtop=(screen.get_width() // 2, 70)))
        tag = small.render(
            "Your body is the controller. Your shadow is your fighter.", True, (170, 170, 170)
        )
        screen.blit(tag, tag.get_rect(midtop=(screen.get_width() // 2, 180)))

        if entering_ip:
            prompt = font.render("Host IP: " + ip_text + "_", True, (255, 255, 255))
            screen.blit(prompt, prompt.get_rect(center=screen.get_rect().center))
            hint = small.render("Enter to connect, Esc to cancel", True, (150, 150, 150))
            screen.blit(hint, hint.get_rect(midtop=(screen.get_width() // 2, screen.get_height() // 2 + 50)))
        else:
            for i, (label, _) in enumerate(MENU_ITEMS):
                color = (255, 220, 90) if i == selected else (210, 210, 210)
                prefix = "> " if i == selected else "   "
                surf = font.render(prefix + label, True, color)
                screen.blit(surf, (screen.get_width() // 2 - 220, 300 + i * 70))

        pygame.display.flip()
        clock.tick(30)
