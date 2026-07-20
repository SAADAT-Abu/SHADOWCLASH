"""Single-player VS mode: a 10-level villain ladder with rising difficulty.

Each level is a full match — rounds, timer, KO — against a named boss whose
attack rate and strike speed escalate (faster strikes also hit harder, since
damage scales with limb velocity). Beat a boss to unlock the next; the champion
run ends at SHADOW KING.
"""

import time

import pygame

from shadowclash.capture.pose_capture import PoseCapture
from shadowclash.capture.synthetic_pose import SyntheticPoseDriver
from shadowclash.physics.collision_engine import CollisionEngine
from shadowclash.physics.damage_system import DamageSystem
from shadowclash.physics.hitbox_manager import FighterHitboxes
from shadowclash.skeleton import skeleton_model as sm
from shadowclash.skeleton.skeleton_renderer import draw_skeleton
from shadowclash.ui.hud import Hud
from shadowclash.ui.scene import FightScene
from shadowclash.ui.sound import SoundBank
from shadowclash.utils.logger import get_logger

log = get_logger(__name__)

LOCAL_COLOR = (70, 160, 255)

# (name, skeleton color, difficulty knobs) — level 1 first, boss last.
# Movesets grow with the ladder: early bosses jab and slap, mid bosses kick,
# late bosses add flying kicks and somersaults.
VILLAINS = [
    ("STREET PUNK", (200, 130, 110), dict(
        attack_interval=(1.6, 2.6), attack_duration=0.55,
        move_weights={"jab": 0.8, "slap": 0.2})),
    ("ALLEY CAT", (220, 150, 90), dict(
        attack_interval=(1.4, 2.3), attack_duration=0.50,
        move_weights={"jab": 0.5, "slap": 0.4, "kick": 0.1})),
    ("IRON JAB", (200, 195, 110), dict(
        attack_interval=(1.2, 2.0), attack_duration=0.46,
        move_weights={"jab": 0.7, "slap": 0.1, "kick": 0.2})),
    ("BONE BREAKER", (160, 205, 130), dict(
        attack_interval=(1.0, 1.8), attack_duration=0.42,
        move_weights={"jab": 0.45, "slap": 0.2, "kick": 0.35})),
    ("VIPER QUEEN", (110, 210, 150), dict(
        attack_interval=(0.9, 1.6), attack_duration=0.38,
        move_weights={"jab": 0.35, "slap": 0.3, "kick": 0.25, "flying_kick": 0.1})),
    ("THUNDER KNEE", (105, 200, 210), dict(
        attack_interval=(0.8, 1.4), attack_duration=0.35,
        move_weights={"jab": 0.2, "slap": 0.1, "kick": 0.5, "flying_kick": 0.2})),
    ("CRIMSON MANTIS", (150, 150, 235), dict(
        attack_interval=(0.7, 1.2), attack_duration=0.33,
        move_weights={"jab": 0.3, "slap": 0.2, "kick": 0.2, "flying_kick": 0.15, "somersault": 0.15})),
    ("GHOST BLADE", (195, 130, 235), dict(
        attack_interval=(0.6, 1.0), attack_duration=0.30,
        move_weights={"jab": 0.25, "slap": 0.25, "kick": 0.2, "flying_kick": 0.15, "somersault": 0.15})),
    ("WAR DEMON", (235, 110, 185), dict(
        attack_interval=(0.5, 0.9), attack_duration=0.28,
        move_weights={"jab": 0.2, "slap": 0.15, "kick": 0.25, "flying_kick": 0.25, "somersault": 0.15})),
    ("SHADOW KING", (255, 85, 65), dict(
        attack_interval=(0.4, 0.75), attack_duration=0.26,
        move_weights={"jab": 0.2, "slap": 0.15, "kick": 0.2, "flying_kick": 0.25, "somersault": 0.2})),
]

# Distance coach: acceptable ratio of player torso to opponent torso
RATIO_TOO_FAR = 0.8
RATIO_TOO_CLOSE = 1.25


def distance_hint(player_torso: float, opponent_torso: float) -> str | None:
    """Suggest camera distance so both fighters render at the same scale."""
    ratio = player_torso / max(opponent_torso, 1e-6)
    if ratio < RATIO_TOO_FAR:
        return "step CLOSER to the camera"
    if ratio > RATIO_TOO_CLOSE:
        return "step BACK from the camera"
    return None


def run_versus(config: dict) -> None:
    pygame.init()
    disp = config["display"]
    screen = pygame.display.set_mode((disp["width"], disp["height"]))
    pygame.display.set_caption("SHADOWCLASH")
    clock = pygame.time.Clock()
    arena = screen.get_rect()

    from shadowclash.ui.menu import run_name_entry, run_settings_panel

    player_name = run_name_entry(screen, config)
    if player_name is None or not run_settings_panel(
        screen, config, "SINGLE PLAYER",
        "villain ladder: beat all 10 bosses (camera stays off until you start)",
    ):
        pygame.quit()
        return

    capture = PoseCapture(config)
    capture.start()

    damage = DamageSystem(config, fighters=("A", "B"))
    engine = CollisionEngine(config, damage)
    player = FighterHitboxes(engine.space, "A")
    shadow = FighterHitboxes(engine.space, "B")
    hud = Hud(screen)
    scene = FightScene(arena.size)
    sounds = SoundBank()

    starting_hp = config["match"]["starting_hp"]
    round_time = config["match"]["round_time_seconds"]

    level = 0
    villain_name, villain_color, villain_params = VILLAINS[level]
    bot = SyntheticPoseDriver(config, **villain_params)
    round_start = time.monotonic()
    ko_message: str | None = None
    ko_sub = ""
    won_level = False
    show_debug = False
    bell_rung = False
    smoothed_ratio = 1.0
    running = True
    log.info("VS ladder started — Esc quits, R rematch/next, D toggles debug")

    def start_level(new_level: int) -> None:
        nonlocal level, villain_name, villain_color, villain_params, bot
        nonlocal round_start, ko_message, won_level, bell_rung
        level = new_level
        villain_name, villain_color, villain_params = VILLAINS[level]
        bot = SyntheticPoseDriver(config, **villain_params)
        damage.reset()
        round_start = time.monotonic()
        ko_message = None
        won_level = False
        bell_rung = False
        log.info("Level %d: %s", level + 1, villain_name)

    while running:
        dt = clock.tick(disp["fps"]) / 1000.0
        now = time.monotonic()
        now_ms = now * 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_d:
                    show_debug = not show_debug
                elif event.key == pygame.K_r and ko_message is not None:
                    if won_level and level < len(VILLAINS) - 1:
                        start_level(level + 1)
                    else:
                        start_level(level)  # retry, or replay the final boss

        local_pose, _ = capture.get_pose()
        bot_pose, _ = bot.get_pose()

        local_xy = None
        if local_pose is not None:
            local_xy = sm.to_arena(local_pose)
            player.update(local_xy, dt)
            if not bell_rung:
                sounds.bell()  # first pose lock = fight on
                bell_rung = True
        bot_xy = sm.to_arena(bot_pose, flip=True)
        shadow.update(bot_xy, dt)

        if ko_message is None and local_xy is not None:
            for hit in engine.check_strikes(player, "B", now_ms, defender_xy=bot_xy):
                pos = hit_zone_px(bot_xy, hit.zone, arena)
                hud.add_hit_popup(hit.zone, hit.damage, hit.blocked, pos)
                scene.add_hit_spark(pos, heavy=hit.zone == "head")
                sounds.hit(hit.zone, hit.damage, hit.blocked)
            for hit in engine.check_strikes(shadow, "A", now_ms, defender_xy=local_xy):
                pos = hit_zone_px(local_xy, hit.zone, arena)
                hud.add_hit_popup(hit.zone, hit.damage, hit.blocked, pos)
                scene.add_hit_spark(pos, heavy=hit.zone == "head")
                sounds.hit(hit.zone, hit.damage, hit.blocked)

        seconds_left = round_time - (now - round_start)
        if ko_message is None:
            player_won = damage.is_ko("B") or (
                seconds_left <= 0 and damage.hp["A"] > damage.hp["B"]
            )
            player_lost = damage.is_ko("A") or (
                seconds_left <= 0 and damage.hp["A"] < damage.hp["B"]
            )
            if player_won:
                won_level = True
                if level == len(VILLAINS) - 1:
                    ko_message = f"{player_name} IS CHAMPION!"
                    ko_sub = f"{villain_name} defeated, all 10 bosses down! R replay, Esc exit"
                else:
                    ko_message = f"{player_name} WINS"
                    ko_sub = f"{villain_name} down! R fight level {level + 2}: {VILLAINS[level + 1][0]}, Esc exit"
            elif player_lost:
                ko_message = f"{villain_name} WINS"
                ko_sub = f"{player_name} is down, R retry, Esc exit"
            elif seconds_left <= 0:
                ko_message = "TIME UP: DRAW"
                ko_sub = "R retry, Esc exit"
            if ko_message is not None:
                bot.fighting = False  # the villain stops swinging after the round ends
                sounds.ko()

        scene.draw_background(screen)
        if local_xy is not None:
            scene.draw_fighter_shadow(screen, local_xy, arena)
        scene.draw_fighter_shadow(screen, bot_xy, arena)
        if local_xy is not None:
            draw_skeleton(screen, local_xy, LOCAL_COLOR, arena, visibility=local_pose[:, 3])
        draw_skeleton(screen, bot_xy, villain_color, arena, visibility=bot_pose[:, 3])
        scene.update_and_draw_particles(screen, dt)

        hud.draw_health_bar(player_name, damage.hp["A"], starting_hp)
        hud.draw_health_bar(villain_name, damage.hp["B"], starting_hp, right=True)
        hud.draw_timer(seconds_left if ko_message is None else 0)
        hud.draw_level_banner(f"LEVEL {level + 1}/{len(VILLAINS)}: {villain_name}")
        hud.draw_popups()

        if local_xy is not None and ko_message is None:
            ratio = sm.torso_length(local_xy) / sm.torso_length(bot_xy)
            smoothed_ratio += (ratio - smoothed_ratio) * min(dt * 3.0, 1.0)
            hint = distance_hint(smoothed_ratio, 1.0)
            if hint is not None:
                hud.draw_distance_hint(hint)

        if local_xy is None:
            hud.draw_center_message("NO POSE", "step into the camera view")
        elif ko_message is not None:
            hud.draw_center_message(ko_message, ko_sub)
        if show_debug:
            fastest = max((v for _, v in player.strikes.values()), default=0.0)
            hud.draw_debug(
                [
                    f"render fps: {clock.get_fps():.0f}   capture fps: {capture.capture_fps:.0f}",
                    f"limb velocity: {fastest:.2f} (threshold {engine.min_strike_velocity})",
                    f"torso ratio: {smoothed_ratio:.2f}",
                ]
            )
        pygame.display.flip()

    capture.stop()
    pygame.quit()


def hit_zone_px(xy, zone: str, arena: pygame.Rect) -> tuple[int, int]:
    if zone == sm.ZONE_HEAD:
        point = sm.head_center(xy)
    elif zone == sm.ZONE_TORSO:
        top, bottom, _ = sm.torso_endpoints(xy)
        point = (top + bottom) / 2.0
    else:
        point = (xy[sm.LEFT_KNEE] + xy[sm.RIGHT_KNEE]) / 2.0
    return (int(arena.x + point[0] * arena.width), int(arena.y + point[1] * arena.height))
